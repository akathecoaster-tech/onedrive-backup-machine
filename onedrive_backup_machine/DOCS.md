# OneDrive Backup Machine

Turns your Home Assistant host into a local backup target for selected OneDrive folders.

## What it does

- Authenticates to Microsoft with a device-code login
- Downloads OneDrive files/folders to local disk (`backup_root`)
- Supports scheduled tasks (cron expressions)
- Exposes a local HTTP API for the companion HACS integration

## Options

### `client_id`

Azure App Registration application ID. Required for login.

### `backup_root`

Where files are stored inside Home Assistant mounts. Default:

`/share/onedrive_backup_machine`

### `listen_port`

Host port for the API/UI. Default `8080`. Point the HACS integration `addon_url` at this port.

## First-run checklist

1. Set `client_id` and start the add-on.
2. Open the add-on UI.
3. Click **Login to OneDrive**, complete the device code in the browser, then **Complete login**.
4. Click **Run backup now** or wait for the schedule.
5. Optionally install the HACS integration and set:

```yaml
onedrive_backup:
  addon_url: http://127.0.0.1:8080
```

## Difference from Core OneDrive

Home Assistant Core's OneDrive integration uploads **Home Assistant backups** to OneDrive.  
This add-on downloads **your OneDrive files** to local storage.
