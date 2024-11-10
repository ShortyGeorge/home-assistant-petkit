import asyncio
from petkitaio import PetKitClient
from datetime import datetime
import aiohttp
from pprint import pprint

async def test_manual_feed():
    # Initialize PetKit client
    email = "0.mains.flory@icloud.com"
    password = "qumbIc-kaxwip"

    async with aiohttp.ClientSession() as session:
        client = PetKitClient(email, password,
            region="United States",
            session=session,
            timeout=20,
        )

        try:
            # Get all devices
            devices = await client.get_petkit_data()

            # Find D4s feeders
            for feeder_id, feeder in devices.feeders.items():
                print(f"\nFeeder: {feeder}")
                if feeder.type == 'feedermini':
                    print(f"\nFeeder: {feeder.data['name']} (ID: {feeder_id})")

                    # Print current food level
                    print(f"Food Level: {feeder.data['state']['food']}")  # 1 means has food, 0 means empty

                    # Print feeding schedule
                    feed_data = feeder.data['feed']
                    print("\nFeeding Schedule:")
                    print(f"Repeats on days: {feed_data['repeats']}")  # 1-7 represents days of week

                    print("\nScheduled Feedings:")
                    for item in feed_data['items']:
                        # Convert seconds since midnight to time
                        seconds = item['time']
                        hours = seconds // 3600
                        minutes = (seconds % 3600) // 60
                        time_str = f"{hours:02d}:{minutes:02d}"

                        print(f"- {item['name']}: {time_str}, Amount: {item['amount']}g")

                    print("\nFeeder Settings:")
                    print(f"Feed notifications: {feeder.data['settings']['feedNotify']}")
                    print(f"Food notifications: {feeder.data['settings']['foodNotify']}")
                    print(f"Battery notifications: {feeder.data['settings']['reBatteryNotify']}")
                    print(f"Manual lock: {feeder.data['settings']['manualLock']}")
                    print(f"Feeder data keys: {feeder.data.keys()}")
                    print(f"Feeder data keys: {feeder.data['feed']}")

                    print("\nFeeder State:")
                    state = feeder.data['state']
                    print(f"Battery Power: {state['batteryPower']}")
                    print(f"Battery Status: {state['batteryStatus']}")
                    print(f"Currently Feeding: {state['feeding']}")
                    print(f"Runtime: {state['runtime']} seconds")

                    # Let's also get the device history if available
                    try:
                        history = await client.get_device_history(feeder)
                        print("\nFeeding History:")
                        pprint(history)
                    except Exception as e:
                        print(f"\nCouldn't get history: {e}")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_manual_feed())
