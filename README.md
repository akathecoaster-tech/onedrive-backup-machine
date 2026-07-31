# OneDrive Backup Machine

Home Assistant **Supervisor add-on** that downloads selected OneDrive folders to local storage on a schedule.

This is the opposite of the official Home Assistant Core [OneDrive](https://www.home-assistant.io/integrations/onedrive/) integration:

| | Core `onedrive` | This add-on |
| --- | --- | --- |
| Direction | HA backups → OneDrive | OneDrive files → local disk |
| Purpose | Backup Home Assistant | Keep a local copy of cloud files |
| UI / API | HA backup system | Add-on web UI + local HTTP API |

Companion HACS integration (dashboard sensors/buttons):  
https://github.com/augleao/onedrive-backup-machine-integration

## Install (Supervisor)

1. In Home Assistant go to **Settings → Add-ons → Add-on Store**.
2. Open the three-dot menu → **Repositories**.
3. Add:

   `https://github.com/augleao/onedrive-backup-machine`

4. Install **OneDrive Backup Machine**.
5. Configure options (see below), start the add-on, open the UI, and complete Microsoft device login.

## Configuration

| Option | Description |
| --- | --- |
| `client_id` | Azure App Registration application (client) ID |
| `backup_root` | Local folder for downloaded files (default `/share/onedrive_backup_machine`) |
| `listen_port` | API/UI port mapped to the host (default `8080`) |

### Create an Azure public client

1. Open [Microsoft Entra app registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade).
2. **New registration** → account type: **Personal Microsoft accounts only** (or combined).
3. No redirect URI is required for device code flow.
4. After creation, copy the **Application (client) ID** into the add-on `client_id` option.
5. Under **Authentication**, enable **Allow public client flows**.
6. Under **API permissions**, add Microsoft Graph delegated permissions:
   - `Files.Read.All`
   - `User.Read`
   - `offline_access`
7. Grant admin consent if your tenant requires it (personal accounts usually do not).

## Local API (used by the HACS integration)

Base URL from Home Assistant host networking / port mapping, commonly:

`http://127.0.0.1:8080`

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/status` | Auth/running status |
| `GET` | `/api/tasks` | List tasks |
| `GET` | `/api/jobs` | List recent jobs |
| `POST` | `/api/backup` | Run the default/first task |
| `POST` | `/api/tasks/{task_id}/run` | Run a specific task |
| `POST` | `/api/login/start` | Start Microsoft device login |
| `POST` | `/api/login/complete` | Finish device login |
| `POST` | `/api/tasks` | Create/update a task |

### Example task payload

```json
{
  "id": "docs",
  "name": "Documents",
  "remote_path": "Documents",
  "mode": "incremental",
  "schedule": "0 3 * * *",
  "enabled": true
}
```

`mode`:
- `incremental` — update `backup_root/<task_id>/latest`, skipping unchanged files
- `full` — write a new timestamped snapshot under `backup_root/<task_id>/`

## Pair with the HACS integration

In `configuration.yaml`:

```yaml
onedrive_backup:
  addon_url: http://127.0.0.1:8080
  scan_interval: 30
```

## Security notes

- Do not commit secrets, recovery codes, or token caches.
- Token cache lives in the add-on `/data` directory.
- This add-on requests read access to OneDrive files in order to download them locally.

## Development

```bash
export ODBM_CLIENT_ID="your-app-id"
export ODBM_BACKUP_ROOT="/tmp/odbm-backups"
export ODBM_DATA_DIR="/tmp/odbm-data"
export ODBM_LISTEN_PORT=8080
python3 onedrive_backup_machine/rootfs/app/main.py
```

## License

MIT
