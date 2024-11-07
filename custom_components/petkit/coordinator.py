"""DataUpdateCoordinator for the PetKit integration."""
from __future__ import annotations

from datetime import timedelta

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

    async def _async_update_data(self) -> PetKitData:
        """Fetch data from PetKit."""

        try:
            data = await self.client.get_petkit_data()
            LOGGER.debug(f'Found the following PetKit devices/pets: {data}')

            # Check for feedings since last update
            for feeder_id, feeder_data in data.feeders.items():
                # Initialize if not exists
                if feeder_id not in self.food_dispensed:
                    self.food_dispensed[feeder_id] = 0

                # Check scheduled feedings
                if 'feed' in feeder_data.data:
                    feed_state = feeder_data.data['state'].get('feedState', {})
                    current_amount = feed_state.get('realAmountTotal', 0)

                    # Get previous amount from coordinator data if exists
                    previous_amount = 0
                    if hasattr(self, 'data') and self.data:
                        previous_feeder = self.data.feeders.get(feeder_id)
                        if previous_feeder:
                            previous_amount = previous_feeder.data['state'].get('feedState', {}).get('realAmountTotal', 0)
                        LOGGER.debug(f'Checking previous amount for feeder {feeder_id} - {previous_amount} vs {current_amount}')

                    # If there's a difference, update the total
                    if current_amount > previous_amount:
                        amount_difference = current_amount - previous_amount
                        self.food_dispensed[feeder_id] += amount_difference
                        LOGGER.debug(f'Feeder {feeder_id} dispensed {amount_difference} grams of food')

                        # Notify any registered food dispensed sensors
                        for entity in self.hass.data[DOMAIN][self.config_entry.entry_id].get("entities", []):
                            if isinstance(entity, FoodDispensedHistory) and entity.feeder_id == feeder_id:
                                entity.log_feeding(amount_difference)
                                break

        except (AuthError, RegionError) as error:
            raise ConfigEntryAuthFailed(error) from error
        except (ServerError, PetKitError) as error:
            raise UpdateFailed(error) from error
        else:
            return data
