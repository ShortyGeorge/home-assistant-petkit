"""DataUpdateCoordinator for the PetKit integration."""
from __future__ import annotations

from datetime import datetime, timedelta, date, timezone

from petkitaio import PetKitClient
from petkitaio.exceptions import AuthError, PetKitError, RegionError, ServerError
from petkitaio.model import PetKitData

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, LOGGER, POLLING_INTERVAL, REGION, TIMEOUT, TIMEZONE


class PetKitDataUpdateCoordinator(DataUpdateCoordinator):
    """PetKit Data Update Coordinator."""

    data: PetKitData

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the PetKit coordinator."""
        self.food_dispensed = {}
        self.accounted_feedings = {}
        self.today_date = date.today()

        if entry.options[TIMEZONE] == "Set Automatically":
            tz = None
        else:
            tz = entry.options[TIMEZONE]
        try:
            self.client = PetKitClient(
                entry.data[CONF_EMAIL],
                entry.data[CONF_PASSWORD],
                session=async_get_clientsession(hass),
                region=entry.options[REGION],
                timezone=tz,
                timeout=TIMEOUT,
            )
            super().__init__(
                hass,
                LOGGER,
                name=DOMAIN,
                update_interval=timedelta(seconds=entry.options[POLLING_INTERVAL]),
            )
        except RegionError as error:
            raise ConfigEntryAuthFailed(error) from error

    async def _async_update_data(self):
        """Fetch data from PetKit."""
        try:
            data = await self.client.get_petkit_data()
            LOGGER.debug('Fetched PetKit data')

            # Initialize daily counters if needed
            if not hasattr(self, 'today_date') or date.today() != self.today_date:
                # Reset daily counters
                self.food_dispensed = {}
                self.accounted_feedings = {}
                self.today_date = date.today()
                LOGGER.debug("Date change detected, reset daily counters.")

            for feeder_id, feeder_data in data.feeders.items():
                # Initialize if not exists
                if feeder_id not in self.food_dispensed:
                    self.food_dispensed[feeder_id] = 0

                if feeder_id not in self.accounted_feedings:
                    self.accounted_feedings[feeder_id] = set()

                # Get feeder timezone offset and create timezone object
                feeder_timezone_offset = feeder_data.data.get('timezone', 0)  # in hours
                feeder_timezone = timezone(timedelta(hours=feeder_timezone_offset))

                feeder_now = datetime.now(feeder_timezone)
                feeder_now_seconds = (
                    feeder_now.hour * 3600 + feeder_now.minute * 60 + feeder_now.second
                )
                LOGGER.debug(
                    f"Feeder {feeder_id} current time (seconds since midnight): {feeder_now_seconds}"
                )

                # Process scheduled feedings
                feed_data = feeder_data.data.get('feed', {})
                items = feed_data.get('items', [])

                for item in items:
                    scheduled_time = item.get('time', 0)  # in seconds since midnight
                    amount = item.get('amount', 0)

                    # If scheduled_time has passed and not already accounted for
                    if (
                        scheduled_time <= feeder_now_seconds
                        and scheduled_time not in self.accounted_feedings.get(feeder_id, set())
                    ):
                        self.accounted_feedings.setdefault(feeder_id, set()).add(scheduled_time)

                        # Fire an event for the scheduled feed
                        self.hass.bus.async_fire(
                            'petkit_scheduled_feed',
                            {'feeder_id': feeder_id, 'amount': amount},
                        )
                        LOGGER.debug(
                            f"Detected scheduled feeding of {amount}g at {scheduled_time}s for feeder {feeder_id}"
                        )

            return data

        except (AuthError, RegionError) as error:
            raise ConfigEntryAuthFailed(error) from error
        except (ServerError, PetKitError) as error:
            raise UpdateFailed(error) from error
