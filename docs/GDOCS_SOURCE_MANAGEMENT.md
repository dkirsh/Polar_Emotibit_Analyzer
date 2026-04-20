# Ground-Truth Source Management

For absolute clinical and scientific integrity, this Post-Hoc Analyzer **does not** permanently harbor raw, un-verified data or participant consent forms. All such "source of truth" materials must be managed outside of this software stack in a secure, backed-up environment like Google Docs/Google Drive.

## Step 1: The Project Root Folder
In your secure Google Drive, create a Master Folder for your study: `[STUDY_ID] EmotiBit-Polar Data`.

## Step 2: The Session Subfolders
For each time a participant sits for a collection phase, you must create a Subfolder named by the `SESSION_ID` (e.g., `S204_2026_04_08`).

Inside this folder, you MUST store:
1. **The Consent Form** (Digital or Scanned PDF) signed by the participant.
2. **The Output CSVs** directly exported from the Polar H10 (via app) and EmotiBit (via SD Card). Name them `S204_polar.csv` and `S204_emotibit.csv`.
3. **The Event Timeline Log** (`S204_markers.csv` or a Google Sheet logging exact UTC times for `recording_start`, `stress_task`, etc.)

## Step 3: Link to the Analyzer
Once the Session Subfolder is complete on Google Drive, launch the Physiological Post-Hoc Analyzer. 
1. Enter the `Subject ID` and `Project ID`.
2. Drag and drop the specific files from your local sync copy of the GDrive folder directly into the Analyzer's dashboard.

By keeping the raw files in Google Drive, you ensure they are securely backed up, permissioned, and auditable, while the Analyzer solely acts as your mathematical sync/extraction engine.
