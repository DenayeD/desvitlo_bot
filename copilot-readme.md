# Electricity Checker Telegram Bot - Project Documentation

## Overview
This is a Telegram bot written in Python using the aiogram 3.0 framework that monitors electricity outage schedules from the Ukrainian energy company website (desvitlo.com.ua) and sends notifications to users about outages in their registered addresses.

## Architecture

### Core Technologies
- **Python 3.x**
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
inspect_db.py       # Database inspection utility
requirements.txt    # Python dependencies
.env                # Environment variables (BOT_TOKEN, ADMIN_USER_ID)
users.db            # SQLite database for user data
test_users.db       # Test database
```

## Database Schema

### Tables
1. **users** - User information
   - user_id (INTEGER PRIMARY KEY)
   - username (TEXT)
   - first_name (TEXT)
   - last_name (TEXT)

2. **addresses** - User addresses
   - id (INTEGER PRIMARY KEY AUTOINCREMENT)
   - user_id (INTEGER)
   - name (TEXT) - User-friendly address name
   - address (TEXT) - Full address for scraping
   - queue (TEXT) - Queue number (1 or 2)

3. **user_notifications** - Notification settings
   - user_id (INTEGER)
   - address_name (TEXT, NULL for global settings)
   - notifications_enabled (INTEGER) - Outage notifications
   - new_schedule_enabled (INTEGER) - New schedule notifications
   - schedule_changes_enabled (INTEGER) - Schedule change notifications

## Key Functions

### Database Functions
- `init_db()` - Creates all database tables
- `get_user_addresses(user_id)` - Returns list of user's addresses
- `add_user_address(user_id, name, address, queue)` - Adds new address
- `get_user_notification_settings(user_id, address_name=None)` - Gets notification settings
- `set_user_notification_settings(user_id, address_name, ...)` - Updates notification settings

### Monitoring Functions
- `monitor_job()` - Main monitoring function that runs every 30 minutes
- `parse_schedule(address, queue)` - Scrapes schedule data from website
- `send_schedule_logic(user_id, address_name, schedule_data, is_new=False)` - Sends schedule notifications

### Bot Handlers
- `/start` - Initial setup and welcome
- `/help` - Help message
- `/menu` - Main menu
- Address management: add, edit, delete addresses
- Settings: global and per-address notification controls
- Queue management: switch between queue 1 and 2

## Notification System

### Types of Notifications
1. **Outage Notifications** - Real-time alerts when outages are detected
2. **New Schedule Notifications** - When a new schedule is published
3. **Schedule Change Notifications** - When existing schedules are modified

### Settings Hierarchy
- **Global Settings**: Apply to all addresses (new schedules, schedule changes)
- **Address Settings**: Per-address outage notifications only

### Grouping Logic
- Multiple addresses with outages in the same time slot are grouped into single messages
- Different outage times send separate messages
- Schedule notifications are sent per address

## Web Scraping

### Target Website
- **URL**: https://hoe.com.ua/
- **Full url for scrap** - https://hoe.com.ua/page/pogodinni-vidkljuchennja
- **Structure**: Addresses are organized by region/city
- **Data Format**: HTML tables with outage schedules

### Parsing Logic
- Uses BeautifulSoup4 to extract schedule tables
- Handles two queues (1 and 2) for each address
- Converts relative times to absolute datetime objects
- Detects schedule changes by comparing with stored data

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
- Automatic font fallback for different systems

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

### AddressStates
- `waiting_for_new_name` - Adding new address name
- `waiting_for_new_address` - Adding new address URL
- `waiting_for_edit_name` - Editing address name
- `waiting_for_edit_address` - Editing address URL

## Error Handling

### Logging
- Uses Python's logging module
- Logs to console and potentially files
- Error levels: INFO, WARNING, ERROR

### Exception Handling
- Database operations wrapped in try/catch
- Web scraping failures logged but don't crash bot
- Network timeouts handled gracefully

## Security Considerations

### Environment Variables
- BOT_TOKEN stored securely (not in code)
- ADMIN_USER_ID for privileged operations
- No hardcoded credentials

### Input Validation
- User inputs sanitized
- URL validation for addresses
- SQL injection prevention via parameterized queries

## Testing

### Test Files
- `test.py` - Extended version with additional test features
- `test_users.db` - Separate database for testing
- `test_clocks/` - Directory for generated test images

### Manual Testing
- Bot can be run in test mode with different database
- Inspect database with `inspect_db.py`

## Known Issues & Future Improvements

### Current Limitations
- Web scraping depends on website structure stability
- No rate limiting for web requests
- Single-threaded monitoring job

### Potential Enhancements
- Multiple bot instances for load balancing
- Webhook support instead of polling
- Advanced scheduling options
- User feedback system
- Multi-language support

## API Usage

### Telegram Bot API
- Uses aiogram's high-level API
- Callback queries for inline keyboards
- Message editing for dynamic UIs
- FSM for multi-step conversations

### External APIs
- None (pure web scraping)

## Code Style & Conventions

### Naming
- Functions: snake_case
- Variables: snake_case
- Constants: UPPER_CASE
- Classes: PascalCase (minimal use)

### Structure
- Database functions at top
- Handler functions grouped by functionality
- Utility functions interspersed as needed
- Main execution at bottom

### Comments
- Ukrainian comments for UI text
- English comments for technical logic
- Docstrings minimal (could be improved)

## Troubleshooting

### Common Issues
1. **Bot not responding**: Check BOT_TOKEN in .env
2. **Database errors**: Ensure write permissions for users.db
3. **Web scraping fails**: Website structure may have changed
4. **Images not generating**: Check font availability

### Debug Mode
- Run with logging level DEBUG
- Check console output for errors
- Use `inspect_db.py` to verify database state

## Maintenance

### Regular Tasks
- Monitor website for structural changes
- Update dependencies periodically
- Backup database regularly
- Check bot uptime and restart if needed

### Code Updates
- Test changes in test environment first
- Update documentation when making significant changes
- Version control all changes

---

This documentation provides comprehensive information about the Electricity Checker bot codebase. For specific implementation details, refer to the inline comments and function docstrings in the source code.