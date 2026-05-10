"""Temporal Analysis meta-strategy module."""

NAME = "temporal_analysis"
DISPLAY_NAME = "Temporal Analysis"
DESCRIPTION = "Timeline-first investigation discipline: chronolocation, EXIF analysis, archive scrub detection, pattern-of-life."
TRIGGER_SIGNALS = [
    "when", "timeline", "history", "sequence", "before", "after", "date",
    "chronology", "event", "incident", "change", "version", "scrubbed",
    "deleted", "edited", "modified",
]
ENTITY_TYPES = ["all"]
ALWAYS_ON = False

STRATEGY_TEXT = """
=== TEMPORAL ANALYSIS META-STRATEGY ===

TIMELINE_FIRST: Build master timeline BEFORE narrative. Event log: timestamp | actor | event | source | confidence.
  detectors: gap (no events where expected) | density (unusual clustering) — both = high-priority signals
  rule: do not write narrative until timeline is populated

TEMPORAL_ANCHORING: Extract >=1 time anchor from seed -> filter every time-aware source call.
  expand: +/-1 week -> +/-1 month -> +/-1 year; never leave temporal scope unbounded; normalize timestamps to UTC

REVERSE_CHRONOLOGY: Known end-state -> work backward to cause.
  T0=end-state -> T-1w (immediate precursors) -> T-1m (operational setup) -> T-6m (planning) -> T-origin (root cause)

CHRONOLOCATION / MEDIA_FORENSICS: Never trust stated timestamps; verify via physical observables.
  shadow-angle dating: SunCalc.org (candidate location + date)
  weather archive: Weather Underground by city/date
  EXIF: run_exif_extractor (GPS/device/timestamps — CANDIDATE, strippable/spoofable)
  reverse image search: run_face_search + TinEye + Yandex -> earliest occurrence (floor, not definitive)
  vegetation/season inference: leaf state, snow, clothing weight

ARCHIVE_REPRODUCIBILITY: Archive key findings at T0 (archive.today + Wayback). Re-run at T+7d and T+30d.
  present at T0 but absent at T1 = HIGH-priority finding (subject monitoring); escalate scrubbing detections immediately

PATTERN_OF_LIFE:
  cluster post timestamps -> derive timezone (peak activity +/-2h = likely local hours)
  burst analysis: sudden high-volume clusters = event-driven (crisis/campaign/travel)
  weekly poster silent 3+ weeks = flag potential status change
  cross-platform simultaneous presence at inconsistent locations = VPN/proxy indicator
"""
