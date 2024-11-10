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
            # LOGGER.debug(f'Found the following PetKit devices/pets: {data}')

            # Check for feedings since last update
            for feeder_id, feeder_data in data.feeders.items():
                # Initialize if not exists
                if feeder_id not in self.food_dispensed:
                    self.food_dispensed[feeder_id] = 0

                # Get the total amount dispensed today from the feeder's state
                feeder_state = feeder_data.data.get('state', {})
                current_total = feeder_state.get('realAmountTotal', 0)

                # Get previous total from the last data
                previous_total = 0
                if self.data and self.data.feeders and feeder_id in self.data.feeders:
                    previous_feeder_data = self.data.feeders[feeder_id].data
                    previous_feeder_state = previous_feeder_data.get('state', {})
                    previous_total = previous_feeder_state.get('realAmountTotal', 0)

                # Calculate the difference
                if current_total > previous_total:
                    amount_difference = current_total - previous_total
                    self.food_dispensed[feeder_id] += amount_difference
                    LOGGER.debug(f"Detected feeding of {amount_difference}g for feeder {feeder_id}")

                    # Notify any registered food dispensed sensors
                    for entity in self.hass.data[DOMAIN][self.config_entry.entry_id]["entities"]:
                        if isinstance(entity, FoodDispensedHistory) and entity.feeder_id == feeder_id:
                            entity.log_feeding(amount_difference)
                            break

        except (AuthError, RegionError) as error:
            raise ConfigEntryAuthFailed(error) from error
        except (ServerError, PetKitError) as error:
            raise UpdateFailed(error) from error
        else:
            return data
