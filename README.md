# Fathom Batch Downloader

A local web application to batch download your meeting recordings, transcripts, summaries, and action items from [Fathom.video](https://fathom.video).

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Features

- 📋 **List all your Fathom meetings** with name, date, and participant info
- ☑️ **Batch select meetings** with Select All / Select None controls
- 🎥 **Download video recordings** (extracted via browser automation)
- 📝 **Export transcripts** in both JSON and human-readable text formats
- 📋 **Save AI summaries** as markdown files
- ✅ **Export action items** with assignees and timestamps
- 📁 **Organized folder structure** - each meeting gets its own folder

## Prerequisites

- Python 3.10 or higher
- A Fathom account with API access
- Your Fathom API key (from [Fathom Settings](https://fathom.video/settings))

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/msg43/fathom-batch-downloader.git
   cd fathom-batch-downloader
   ```

2. **Create a virtual environment** (recommended)
   ```bash
   python -m venv venv
   source venv/bin/activate  # On macOS/Linux
   # or
   .\venv\Scripts\activate   # On Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers** (required for video downloads)
   ```bash
   playwright install chromium
   ```

## Usage

1. **Start the application**
   ```bash
   python app.py
   ```

2. **Open your browser** and go to [http://localhost:5000](http://localhost:5000)

3. **Configure your credentials**
   - Enter your Fathom API key and click "Save Configuration"
   - For video downloads: Click "Sign in with Google" - a browser window will open for you to authenticate with your Google account

4. **Load your meetings** by clicking "Load Meetings"

5. **Select meetings** to download using checkboxes

6. **Choose what to download**
   - Video Recording
   - Transcript
   - Summary
   - Action Items

7. **Click "Download Selected Meetings"** and wait for the process to complete

## Download Output Structure

Downloads are saved to the `downloads/` folder with this structure:

```
downloads/
├── 2025-03-01_Quarterly_Business_Review/
│   ├── video.mp4
│   ├── transcript.json
│   ├── transcript.txt
│   ├── summary.md
│   ├── action_items.json
│   ├── action_items.md
│   └── metadata.json
├── 2025-03-02_Team_Standup/
│   └── ...
```

## Configuration

Configuration is stored in `config.json` (automatically created, gitignored):

```json
{
  "api_key": "your-fathom-api-key"
}
```

Google authentication session is stored in `.browser_session/` (also gitignored).

**Note:** All data is stored locally and never transmitted anywhere except to Fathom's servers.

## API Reference

This app uses the [Fathom API](https://developers.fathom.ai/):

- `GET /meetings` - List all meetings with optional filters
- `GET /recordings/{id}/transcript` - Get meeting transcript
- `GET /recordings/{id}/summary` - Get meeting summary

## Troubleshooting

### "Invalid API key" error
- Make sure you've copied the complete API key from Fathom Settings
- Check that there are no extra spaces in the key

### Video download fails
- Make sure you've signed in with Google by clicking the "Sign in with Google" button
- If your session expired, click the button again to re-authenticate
- Some videos may be restricted or unavailable

### Rate limiting
- Fathom limits API calls to 60 per minute
- The app handles this automatically, but large batch downloads may take time

## Security Notes

- All credentials are stored locally in `config.json`
- The config file is gitignored by default
- Video downloads use a headless browser with your Fathom session
- No data is sent to any third-party servers

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This tool is not affiliated with or endorsed by Fathom Video, Inc. Use responsibly and in accordance with Fathom's Terms of Service.

