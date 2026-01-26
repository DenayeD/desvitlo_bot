import json
import logging
import os
from config.settings import CACHE_PATH

def load_cached_schedules():
    """Load cached schedules from file"""
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logging.error(f"Error loading cached schedules: {e}")
        return {}

def save_cached_schedules(cached_schedules):
    """Save cached schedules to file"""
    try:
        # Ensure directory exists
        cache_dir = os.path.dirname(CACHE_PATH)
        logging.info(f"Cache directory: '{cache_dir}', CACHE_PATH: '{CACHE_PATH}'")
        if cache_dir:  # Only create directory if it's not empty
            os.makedirs(cache_dir, exist_ok=True)
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cached_schedules, f, ensure_ascii=False, indent=2)
        logging.info(f"Successfully saved {len(cached_schedules)} cached schedules")
    except Exception as e:
        logging.error(f"Error saving cached schedules: {e}")
        import traceback
        traceback.print_exc()

def get_schedule_for_date(date_key, subqueue):
    """Get schedule for specific date and subqueue from cache"""
    cached = load_cached_schedules()
    date_data = cached.get(date_key, {})
    return date_data.get(subqueue, "")

def update_cached_schedule(date_key, subqueue, schedule_text, schedule_type="full"):
    """
    Update cached schedule
    schedule_type: "full" - complete schedule, "changes" - only changes
    """
    cached = load_cached_schedules()

    if date_key not in cached:
        cached[date_key] = {}

    if schedule_type == "full":
        # Complete schedule update
        cached[date_key][subqueue] = schedule_text
    elif schedule_type == "changes":
        # Supplement existing schedule with changes
        existing = cached[date_key].get(subqueue, "")
        if existing and schedule_text:
            # Merge logic (simplified for now)
            cached[date_key][subqueue] = existing + "; " + schedule_text
        else:
            cached[date_key][subqueue] = schedule_text

    save_cached_schedules(cached)
    logging.info(f"Updated cached schedule for {date_key}, {subqueue}")

async def initialize_cache():
    """Initialize cache with data from site on bot startup"""
    try:
        logging.info("Initializing cache with site data...")
        from utils.monitoring import parse_hoe_smart
        from utils.helpers import normalize_schedule_text

        # Parse site data
        all_data = await parse_hoe_smart()
        if not all_data:
            logging.warning("No data received from site during cache initialization")
            return

        logging.info(f"Received data for {len(all_data)} dates from site")

        # Fill cache with all available schedules
        cached_schedules = {}
        for date_key, data in all_data.items():
            if 'schedules' in data and data['schedules']:
                cached_schedules[date_key] = {}
                for subqueue, schedule_text in data['schedules'].items():
                    normalized_text = normalize_schedule_text(schedule_text)
                    if normalized_text:  # Only save non-empty schedules
                        cached_schedules[date_key][subqueue] = normalized_text
            else:
                logging.info(f"No schedules found for date {date_key}")

        logging.info(f"Prepared cache with {len(cached_schedules)} dates and {sum(len(schedules) for schedules in cached_schedules.values())} schedules")

        # Save to cache file
        save_cached_schedules(cached_schedules)
        logging.info(f"Cache initialized successfully")

        # Generate clocks for all subqueues
        await generate_all_clocks_for_cache(cached_schedules)
        logging.info("Clocks generated for all cached schedules")

    except Exception as e:
        logging.error(f"Error initializing cache: {e}")
        import traceback
        traceback.print_exc()

async def check_and_update_cache():
    """Check for updates on site and update cache/clocks only if changed"""
    try:
        logging.info("Checking for schedule updates...")
        from utils.monitoring import parse_hoe_smart
        from utils.helpers import normalize_schedule_text

        # Parse fresh data from site
        all_data = await parse_hoe_smart()
        if not all_data:
            logging.warning("No data received from site during update check")
            return False, {}

        # Load current cache
        current_cache = load_cached_schedules()

        # Check if data has changed
        has_changes = False
        new_cache = {}
        changes = {}  # date -> {'new': [], 'changed': []}

        for date_key, data in all_data.items():
            if 'schedules' in data and data['schedules']:
                new_cache[date_key] = {}
                changes[date_key] = {'new': [], 'changed': []}
                for subqueue, schedule_text in data['schedules'].items():
                    normalized_text = normalize_schedule_text(schedule_text)
                    if normalized_text:
                        new_cache[date_key][subqueue] = normalized_text

                        # Check if this schedule changed
                        current_schedule = current_cache.get(date_key, {}).get(subqueue, "")
                        if normalized_text != current_schedule:
                            has_changes = True
                            if not current_schedule:
                                changes[date_key]['new'].append(subqueue)
                            else:
                                changes[date_key]['changed'].append(subqueue)
                            logging.info(f"Schedule {'new' if not current_schedule else 'changed'} for {subqueue} on {date_key}")

        if not has_changes:
            logging.info("No schedule changes detected")
            return False, {}

        # Data changed - update cache and regenerate clocks
        logging.info(f"Detected changes, updating cache with {len(new_cache)} dates and {sum(len(schedules) for schedules in new_cache.values())} schedules")

        # Save updated cache
        save_cached_schedules(new_cache)

        # Generate clocks for changed data
        await generate_all_clocks_for_cache(new_cache)
        logging.info("Cache and clocks updated")

        return True, changes

    except Exception as e:
        logging.error(f"Error checking for updates: {e}")
        import traceback
        traceback.print_exc()
        return False, {}

async def generate_all_clocks_for_cache(cached_schedules):
    """Generate clock images for all cached schedules"""
    try:
        from ocr.parser import generate_clock_image

        total_clocks = 0
        for date_key, schedules in cached_schedules.items():
            for subqueue, schedule_text in schedules.items():
                try:
                    # Generate clock image
                    clock_file = generate_clock_image(subqueue, schedule_text, date_key.replace('.', '_'))
                    total_clocks += 1
                    logging.debug(f"Generated clock for {subqueue} on {date_key}")
                except Exception as e:
                    logging.error(f"Error generating clock for {subqueue} on {date_key}: {e}")

        logging.info(f"Generated {total_clocks} clock images")

    except Exception as e:
        logging.error(f"Error generating clocks: {e}")
        import traceback
        traceback.print_exc()

async def update_clock_time_hands():
    """Update time hands on all existing clock images (hourly job)"""
    try:
        logging.info("Updating time hands on clock images...")
        
        # Load current cache to get all schedules
        cached_schedules = load_cached_schedules()
        if not cached_schedules:
            logging.warning("No cached schedules found for clock update")
            return

        # Regenerate all clocks with updated time hands
        await generate_all_clocks_for_cache(cached_schedules)
        logging.info("Time hands updated on all clock images")

    except Exception as e:
        logging.error(f"Error updating clock time hands: {e}")
        import traceback
        traceback.print_exc()