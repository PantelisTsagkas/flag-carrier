# Flag Carrier

STATUS: ACTIVE - office stand-up game, not a portfolio piece

Daily European flag quiz styled as an airport departures board. 10 flags, 10 seconds each, faster answers score more. Everyone gets the same flags each day (seeded by the Europe/London date), your first attempt counts, and the leaderboard settles it at stand-up.

## Play it

Live at https://flag-carrier.fly.dev (Fly.io, single 256MB machine in London that auto-stops when idle, scores on a 1GB volume). Deploy updates with:

```sh
fly deploy --ha=false
```

## Run it (Docker)

```sh
docker compose up -d --build
```

Then open http://localhost:8000. Colleagues on the same network use `http://<your-ip>:8000` (find yours with `ipconfig getifaddr en0` on a Mac). Scores persist in `./data/scores.db`, which is bind-mounted into the container.

## Run it (local dev)

```sh
uv sync
uv run uvicorn main:app --port 8000
uv run pytest
```

## Rules

- 10 legs per day, 10 seconds each. Correct answer scores 100 plus up to 100 speed bonus (max 2000 per day).
- The daily run is identical for everyone: rounds are seeded from the date.
- First submitted score per name per day stands. Replays are never logged, so play your daily run live at stand-up if you want it to count.
- Training flights (practice mode) use random flags and are never logged.
- One name = one player. Pick a name and keep it, the all-time board sums your daily scores into frequent flyer miles.

## Credits

Flag SVGs vendored from [flag-icons](https://github.com/lipis/flag-icons) (MIT), see `static/flags/LICENSE`.
