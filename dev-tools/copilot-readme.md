# Electricity Checker Telegram Bot - Project Documentation

## Overview
This is a Telegram bot written in Python using the aiogram 3.0 framework that monitors electricity outage schedules from the Ukrainian energy company website (hoe.com.ua) and sends notifications to users about outages in their registered addresses and subqueues.

## Architecture

### Core Technologies
- **Python 3.7+**
- **aiogram 3.0** - Telegram bot framework
- **SQLite** - Database for user data and settings
- **APScheduler** - Background job scheduling for periodic monitoring
- **BeautifulSoup4** - HTML parsing for web scraping
- **Pillow (PIL)** - Image generation for schedule visualizations
- **python-dotenv** - Environment variable management

### Project Structure
```
bot.py              # Main bot file with all handlers and logic
main.py             # Alternative entry point (legacy)
server_bot.py       # Server-specific bot version
test.py             # Testing version with additional features
db_inspector.py     # Database inspection utility
inspect_db.py       # Legacy database inspection utility
requirements.txt    # Python dependencies
README.md           # User documentation
DB_INSPECTOR_README.md # Database inspector documentation
.env                # Environment variables (BOT_TOKEN, ADMIN_USER_ID)
users.db            # SQLite database for user data
test_users.db       # Test database
clocks/             # Generated clock images
test_clocks/        # Test clock images
```

## Database Schema

### Tables
1. **users** - Legacy user information (for compatibility)
   - user_id (INTEGER PRIMARY KEY)
   - subqueue (TEXT) - Default subqueue

2. **addresses** - User addresses with subqueues
   - user_id (INTEGER)
   - name (TEXT) - User-friendly address name
   - subqueue (TEXT) - Subqueue number (1.1, 1.2, 2.1, etc.)
   - is_main (BOOLEAN) - Whether this is the main address
   - PRIMARY KEY (user_id, name)

3. **user_notifications** - Notification settings per address
   - user_id (INTEGER)
   - address_name (TEXT, NULL for global settings)
   - notifications_enabled (INTEGER) - Outage notifications
   - new_schedule_enabled (INTEGER) - New schedule notifications
   - schedule_changes_enabled (INTEGER) - Schedule change notifications
   - PRIMARY KEY (user_id, address_name)

4. **settings** - Bot settings and cached data
   - key (TEXT PRIMARY KEY)
   - value (TEXT) - JSON data

5. **sent_alerts** - History of sent notifications
   - user_id (INTEGER)
   - event_time (TEXT) - Time of event
   - event_date (TEXT) - Date of event

## Key Functions

### Database Functions
- `init_db()` - Creates all database tables with proper schema
- `get_user_addresses(user_id)` - Returns list of user's addresses with settings
- `add_user_address(user_id, name, subqueue)` - Adds new address with subqueue
- `get_user_notification_settings(user_id, address_name=None)` - Gets notification settings
- `set_user_notification_settings(user_id, address_name, ...)` - Updates notification settings

### Monitoring Functions
- `monitor_job()` - Main monitoring function that runs every 5 minutes
- `parse_hoe_smart()` - Advanced parsing of schedule data from website
- `send_schedule_logic(chat_id, subqueue, day_type, is_update)` - Sends schedule notifications
- `check_light_status(schedule_text)` - Determines current power status

### Bot Handlers
- `/start` - Initial setup and welcome
- `/broadcast` - Admin broadcast message (admin only)
- `/stats` - Show bot statistics (admin only)
- Address management: add, edit, delete addresses and subqueues
- Settings: global and per-address notification controls
- Schedule viewing: today, tomorrow, general schedule

## Notification System

### Types of Notifications
1. **60-minute warnings** - Alerts 60 minutes before outages start/end
2. **15-minute warnings** - Additional alerts 15 minutes before changes
3. **New schedule notifications** - When new schedules are published
4. **Schedule change notifications** - When existing schedules are modified with detailed before/after comparison
5. **Image update notifications** - When schedule images are updated

### Settings Hierarchy
- **Global Settings**: Apply to all addresses (new schedules, schedule changes)
- **Address Settings**: Per-address outage notifications

### Grouping Logic
- Multiple addresses with outages in the same time slot are grouped into single messages
- Different outage times send separate messages
- Schedule notifications show specific changes per affected subqueue

## Web Scraping

### Target Website
- **URL**: https://hoe.com.ua/page/pogodinni-vidkljuchennja
- **Structure**: Images with alt-text containing dates, followed by HTML lists
- **Data Format**: Subqueue-based schedules with time intervals

### Parsing Logic
- Uses `parse_hoe_smart()` for comprehensive parsing
- Handles multiple dates and subqueues
- Detects new schedules, content changes, and image updates separately
- Normalizes schedule text for accurate comparison

## Image Generation

### Clock Visualization
- Generates circular clock images showing outage periods
- Uses Pillow (PIL) library
- Shows time slots as colored arcs on the clock face
- Includes hour markers and digital time displays

### Features
- 24-hour clock format
- Multiple outage periods per day
- Ukrainian text support
- Automatic cleanup of old images

## Admin Features

### Statistics Command (`/stats`)
Shows comprehensive bot statistics:
- Total users and addresses
- Users with configured/enabled notifications
- Distribution by subqueues
- Total sent notifications

### Database Inspector (`db_inspector.py`)
Command-line tool for detailed database analysis:
```bash
python db_inspector.py          # Analyze users.db
python db_inspector.py file.db   # Analyze specific file
python db_inspector.py --help    # Show help
```

### Broadcast System
Admin can send messages to all users with `/broadcast` command.

## Deployment

### Environment Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with BOT_TOKEN and ADMIN_USER_ID
```

### Running the Bot
```bash
python bot.py
```

### Server Deployment (Linux)
- Uses systemd service for auto-start
- Virtual environment activation
- Log rotation
- Environment variables via .env file

## FSM States

### BroadcastStates
- `waiting_for_message` - Admin composing broadcast message

### AddressStates
- `waiting_for_new_name` - Adding new address name
- `waiting_for_new_queue` - Selecting subqueue for new address
- `waiting_for_edit_name` - Editing address name
- `waiting_for_edit_queue` - Changing subqueue for address

## Error Handling

### Logging
- Uses Python's logging module with INFO level
- Logs to console with timestamps
- Error levels: INFO, WARNING, ERROR

### Exception Handling
- Database operations wrapped in try/catch
- Web scraping failures logged but don't crash bot
- Network timeouts (15s) handled gracefully
- Telegram API errors handled with retries

## Security Considerations

### Environment Variables
- BOT_TOKEN stored securely in .env file
- ADMIN_USER_ID for privileged operations
- No hardcoded credentials in source code

### Input Validation
- User inputs sanitized
- Subqueue validation (1.1-6.2 format)
- SQL injection prevention via parameterized queries

## Testing

### Test Files
- `test.py` - Extended version with additional test features
- `test_users.db` - Separate database for testing
- `test_clocks/` - Directory for generated test images

### Database Inspector
- `db_inspector.py` - Comprehensive database analysis tool
- Shows detailed user information and settings
- Command-line interface for easy automation

## Recent Updates (v2.0+)

### Major Improvements
- **Enhanced Change Notifications**: Shows specific before/after comparisons instead of generic messages
- **15-minute Warnings**: Additional notification tier for imminent changes
- **Admin Statistics**: `/stats` command for bot analytics
- **Database Inspector**: Local analysis tool for database files
- **Improved Parsing**: Better handling of multiple dates and subqueues
- **Image Change Detection**: Separate handling for image vs content updates

### Technical Changes
- Updated database schema with proper relationships
- Improved monitoring logic with 5-minute intervals
- Better error handling and logging
- Enhanced user interface with clearer navigation

## API Usage

### Telegram Bot API
- Uses aiogram 3.0 high-level API
- Callback queries for inline keyboards
- Message editing for dynamic UIs
- FSM for multi-step conversations
- Photo sending with captions

### External Dependencies
- BeautifulSoup4 for HTML parsing
- Pillow for image generation
- APScheduler for background tasks

## Code Style & Conventions

### Naming
- Functions: snake_case
- Variables: snake_case
- Constants: UPPER_CASE
- Classes: PascalCase (States, etc.)

### Structure
- Database functions at top
- Handler functions grouped by functionality
- Utility functions interspersed as needed
- Main execution at bottom with scheduler setup

### Comments
- Ukrainian comments for UI text and strings
- English comments for technical logic
- Function headers with brief descriptions

## Troubleshooting

### Common Issues
1. **Bot not responding**: Check BOT_TOKEN in .env file
2. **Database errors**: Ensure write permissions for users.db
3. **Web scraping fails**: Website structure may have changed
4. **Images not generating**: Check font availability and clocks/ directory permissions
5. **Notifications not working**: Check user notification settings

### Debug Mode
- Run with logging enabled (default INFO level)
- Check console output for errors
- Use `db_inspector.py` to verify database state
- Test with `test.py` for isolated testing

## Maintenance

### Regular Tasks
- Monitor website for structural changes
- Update dependencies periodically
- Backup database regularly
- Check bot uptime and restart if needed
- Clean up old clock images

### Code Updates
- Test changes in test environment first
- Update documentation when making significant changes
- Version control all changes
- Use db_inspector.py to verify database integrity

---

This documentation provides comprehensive information about the Electricity Checker bot codebase. For specific implementation details, refer to the inline comments and function docstrings in the source code.