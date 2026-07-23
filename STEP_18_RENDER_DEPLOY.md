# MoodyAI Step 18 — Render Deployment

## Architecture

- One paid Render web service
- One Docker container
- One persistent disk mounted at `/var/data`
- SQLite database at `/var/data/moodyai.db`
- Verified backups at `/var/data/backups`
- One web worker so background FUB sync and backup jobs do not duplicate

## Local installation

Copy the Step 18 files into the repository, run `install_step18.py`, then run:

```bash
.venv/bin/python -m unittest tests.test_render_deployment -v
.venv/bin/python deployment_check.py
```

## Commit to GitHub

Do not commit `.env`, API keys, credentials, the live SQLite database, or backup files.

```bash
git add Dockerfile .dockerignore render.yaml requirements.txt \
  moodyai_learning/paths.py main.py run_production.py \
  moodyai_learning/production.py prepare_render_database.py \
  tests/test_render_deployment.py STEP_18_RENDER_DEPLOY.md .env.render.example

git commit -m "Add Render deployment configuration"
git push
```

## Create the service

1. Open Render Dashboard.
2. Choose **New → Blueprint**.
3. Select the GitHub repository containing `render.yaml`.
4. Confirm a paid `starter` web service and a 1 GB disk.
5. Enter secret values when prompted:
   - `MOODYAI_ADMIN_PASSWORD`
   - `FOLLOWUPBOSS_API_KEY`
   - `OPENAI_API_KEY` (optional)
6. Deploy.

The Blueprint generates `MOODYAI_SESSION_SECRET` and configures `/ready` as the health check.

## Verify after deployment

```text
https://YOUR-SERVICE.onrender.com/ready
https://YOUR-SERVICE.onrender.com/health
https://YOUR-SERVICE.onrender.com/login
```

`/ready` must return `ready: true`. `/health` should show healthy database, background sync, backups, and authentication.

## Local database migration

Create a verified snapshot locally:

```bash
.venv/bin/python prepare_render_database.py
```

This writes:

```text
render_seed/moodyai.db
render_seed/moodyai.manifest.json
```

Do not commit this database. The first deployment can begin with an empty ledger. A separate controlled migration step should be used to place the seed onto the persistent disk after the service is verified.

## Operational constraints

- Keep exactly one instance while SQLite and in-process schedulers are used.
- Do not use a free service: it cannot attach a persistent disk and may sleep.
- Do not scale horizontally until the scheduler is separated and SQLite is replaced with a shared database.
- Render services with a persistent disk do not have zero-downtime deploys; plan deployments accordingly.
