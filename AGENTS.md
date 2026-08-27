# Optasy agent guide

## Objective

Maintain small, evidence-backed, transparent fantasy-football decision tools.
Prefer improvements that support the user's private league without turning
Optasy into a generalized platform.

## Sources of truth

- `README.md` — public architecture, setup, and operating boundaries
- `config/league.example.yaml` — public configuration schema
- `reports/2026-draft-decision-protocol.md` — prospective decision policy

## Setup and tests

Follow the quick start in `README.md`. The unit suite must pass without
credentials, `config/league.yaml`, or the ignored `data/` tree. Use synthetic
fixtures or small committed non-sensitive inputs for normal changes.

## Privacy and evidence boundaries

- Never commit `.env`, `config/league.yaml`, provider payloads, generated
  boards, or private league history.
- Prospective snapshots, frozen inputs, and decision records are append-only.
  Never overwrite or backfill them after outcomes are known.
- Do not silently treat sample or incomplete provider data as a real baseline.
- Prefer player-agnostic changes supported by evidence, explicit uncertainty,
  a strong alternative, and stated reversal conditions.
