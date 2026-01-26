import re
from datetime import datetime

def check_light_status(schedule_text):
    """Check if there is electricity now based on schedule text"""
    now = datetime.now().time()
    clean_text = schedule_text.replace("з ", "").replace(" до ", "-")
    intervals = re.findall(r"(\d{2}:\d{2})[–\-\—\−](\d{2}:\d{2})", clean_text)
    for start_str, end_str in intervals:
        try:
            start_t = datetime.strptime(start_str, "%H:%M").time()
            if end_str == '24:00':
                end_t = datetime.strptime('23:59', "%H:%M").time()  # Approximately end of day
            else:
                end_t = datetime.strptime(end_str, "%H:%M").time()
            if start_t <= now <= end_t: return False
        except ValueError: continue
    return True

def parse_schedule_to_intervals(schedule_text):
    """
    Parse schedule text into intervals for clock
    Returns dict with guaranteed and possible intervals
    """
    intervals = {
        'guaranteed': [],  # [(start_hour, end_hour), ...]
        'possible': []     # [(start_hour, end_hour), ...]
    }

    if not schedule_text:
        return intervals

    # Split into parts by ";"
    parts = schedule_text.split(';')

    # If only one part - it's guaranteed outages
    if len(parts) == 1:
        text = parts[0].strip()
        if text:
            intervals['guaranteed'].extend(parse_intervals_text(text))
    else:
        # First part - guaranteed, second - possible
        guaranteed_text = parts[0].strip()
        possible_text = parts[1].strip()

        if guaranteed_text:
            intervals['guaranteed'].extend(parse_intervals_text(guaranteed_text))
        if possible_text:
            intervals['possible'].extend(parse_intervals_text(possible_text))

    return intervals

def parse_intervals_text(text):
    """Parse intervals text like '01:00-02:00, 03:00-04:00'"""
    intervals = []
    if not text:
        return intervals

    # Split by commas
    time_ranges = text.split(',')
    for time_range in time_ranges:
        time_range = time_range.strip()
        match = re.search(r'(\d{1,2}):00-(\d{1,2}):00', time_range)
        if match:
            start_hour = int(match.group(1))
            end_hour = int(match.group(2))
            intervals.append((start_hour, end_hour))

    return intervals

def merge_consecutive_intervals(intervals):
    """Merge consecutive time intervals"""
    if not intervals:
        return []

    # Sort intervals by start time
    sorted_intervals = sorted(intervals, key=lambda x: x[0])

    merged = [sorted_intervals[0]]

    for current in sorted_intervals[1:]:
        last = merged[-1]

        # If intervals overlap or are consecutive
        if current[0] <= last[1]:
            # Merge them
            merged[-1] = (last[0], max(last[1], current[1]))
        else:
            merged.append(current)

    return merged

def format_all_periods(intervals):
    """
    Format all periods (outages + power supply) in one block
    Each period on separate line, sorted by time
    """
    # Merge guaranteed intervals
    guaranteed = merge_consecutive_intervals(intervals['guaranteed'])
    possible = merge_consecutive_intervals(intervals['possible'])

    # Collect all outage periods
    all_outages = []
    for start, end in guaranteed:
        all_outages.append((start, end, '🔴', 'guaranteed'))
    for start, end in possible:
        all_outages.append((start, end, '🟡', 'possible'))

    # Sort outages by time
    all_outages.sort(key=lambda x: x[0])

    # Collect all power supply periods
    power_periods = []
    current_time = 0

    for start, end, emoji, outage_type in all_outages:
        if current_time < start:
            power_periods.append((current_time, start, '🟢', 'power'))
        current_time = max(current_time, end)

    if current_time < 24:
        power_periods.append((current_time, 24, '🟢', 'power'))

    # Combine all periods
    all_periods = all_outages + power_periods

    # Sort by start time
    all_periods.sort(key=lambda x: x[0])

    # Format each period on separate line
    formatted_lines = []
    for start, end, emoji, period_type in all_periods:
        time_str = f"{start:02d}:00-{end:02d}:00"
        formatted_lines.append(f"{emoji} {time_str}")

    return formatted_lines

def normalize_schedule_text(text):
    """Normalize schedule text for comparison: strip, replace 'до' with '-', normalize separators."""
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)  # multiple spaces to single
    text = re.sub(r'[–\-\—\−]', '-', text)  # normalize dashes
    text = re.sub(r',\s*з\s+', '; ', text)  # ', з ' to '; '  -- first!
    text = re.sub(r'з\s+', '', text)  # remove 'з '
    text = re.sub(r'\s+до\s+', '-', text)  # ' до ' to '-'
    text = re.sub(r';\s*$', '', text)  # remove trailing ;

    # Handle OCR format: "Вимкнено: 07:00-08:00, 14:00-15:00; Можливо вимкнено: 09:00-10:00"
    if "Вимкнено:" in text or "Можливо вимкнено:" in text:
        parts = []
        if "Вимкнено:" in text:
            off_part = text.split("Вимкнено:")[1].split(";")[0].strip()
            parts.append(off_part)
        if "Можливо вимкнено:" in text:
            possible_part = text.split("Можливо вимкнено:")[1].strip()
            parts.append(possible_part)
        text = "; ".join(parts)

    return text