# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-06-01

Audit-hardening pass. The recurring theme of this release is **never fabricate
medical facts** — every hotline, doctor, hospital, trial, dose, and legal claim
must trace to a live, verifiable source — plus schema convergence and packaging.

### Fixed
- **Crisis hotlines corrected** — `cancer-buddy-mind` crisis resources now cite
  the national psychological-assistance hotline **12356** (and other verified
  numbers); removed stale / unverified numbers.
- **Nutrition drug–food evidence contract** — `cancer-buddy-nutrition`
  drug–food interaction guidance must now carry a traceable evidence anchor;
  no LLM-synthesized interaction claims.
- **find-care never-fabricate gate** — `cancer-buddy-find-care` now refuses to
  invent doctors, hospitals, or trials; results must come from a live source or
  be declined. Output schema fields aligned with the rest of the suite.
- **Disclosure legal citations corrected** — `cancer-buddy-disclosure` legal
  references updated to accurate citations.

### Changed
- **profile.json schema convergence** — patient `profile.json` schema unified
  across companion sub-skills and `references/patient-profile-schema.md`.
- **Trigger-description normalization** — sub-skill trigger descriptions
  normalized for consistent routing from the meta-skill.

### Added
- **Plugin manifests** — `.claude-plugin/plugin.json` and
  `.claude-plugin/marketplace.json` (Claude Code plugin format).
- **Versioning & governance** — `CHANGELOG.md` (Keep a Changelog),
  `CONTRIBUTING.md`, and CI.
- **web-access provenance** — `skills/web-access/VENDOR.md` records the vendored
  upstream (一泽Eze, MIT, 2.5.0).

[Unreleased]: https://github.com/CancerDAO/cancer-buddy-skill/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/CancerDAO/cancer-buddy-skill/releases/tag/v0.2.0
