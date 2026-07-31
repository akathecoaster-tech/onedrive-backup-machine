# Publish this add-on repository

The cloud agent token cannot create new GitHub repositories. Create an empty public repo once, then push.

## Option A — restore the deleted repo (fastest if still available)

1. Open https://github.com/settings/deleted_repositories while logged in as `augleao`
2. If `onedrive-backup-machine` appears, restore it
3. Force-push this clean tree over it:

```bash
cd /opt/cursor/artifacts/onedrive-backup-machine
git remote set-url origin https://github.com/augleao/onedrive-backup-machine.git
git push -u origin main --force
```

Only do a force-push if you intentionally want this clean public release to replace the restored history (recommended after the credential incident).

## Option B — create a new empty public repository

1. Open https://github.com/new
2. Owner: `augleao`
3. Repository name: `onedrive-backup-machine`
4. Public
5. **Do not** add README / license / .gitignore
6. Create repository
7. Push:

```bash
cd /opt/cursor/artifacts/onedrive-backup-machine
git remote set-url origin https://github.com/augleao/onedrive-backup-machine.git
git push -u origin main
```

Or with GitHub CLI from a machine authenticated as you:

```bash
cd /opt/cursor/artifacts/onedrive-backup-machine
gh repo create augleao/onedrive-backup-machine --public --source=. --remote=origin --push
```

## After GitHub is live

1. Open the repo and confirm README + `repository.yaml` are visible
2. Create release tag `v1.0.0` if desired
3. Update/confirm the HACS integration README links here
4. Reply on https://github.com/hacs/default/pull/7865 and mark ready for review
