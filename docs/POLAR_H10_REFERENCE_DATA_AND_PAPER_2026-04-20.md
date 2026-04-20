# Polar H10 reference data and validation paper (2026-04-20 update)

*Date*: 2026-04-20
*Supersedes*: the "Polar H10 sample data" section in `docs/INTEGRATION_PLAN_WITH_SIBLING_REPO_2026-04-20.md` — not the whole plan, only the data-sourcing paragraph, which was written before we had the three URLs DK supplied.

---

## What DK supplied and what each one gives us

**1. OSF project WYM3S — the published companion dataset.** DOI `10.17605/OSF.IO/WYM3S`. This is the project we did not know about when the original audit was written. It is the companion dataset to a 2026 *Sensors* (MDPI) validation paper — Chung, Chopin, Karadayi, and Grèzes at the ENS / PSL Laboratoire de Neurosciences Cognitives et Computationnelles (Paris) — and it carries raw Polar H10 ECG recordings at 133 Hz, computed inter-beat interval (IBI) series, paired gold-standard ECG for comparison, and dyadic recordings (pairs of participants watching the same audiovisual stimulus to test heart-rate synchrony). The dataset was recorded using a custom Python acquisition stack built on **Bleakheart** (a Bleak-based BLE library for the Polar H10) plus the Polar SDK. The deposit is open-access under the OSF project's published license. This is the single most useful dataset the project can test against because it *already* carries a paired reference signal and an already-validated downstream analysis.

**2. PubMed Central PMC12899868 — the paper that validates the dataset.** Citation: Chung, V., Chopin, L., Karadayi, J., & Grèzes, J. (2026). Validity of the Polar H10 for continuous measures of heart rate and heart rate synchrony analysis. *Sensors, 26*(3), 855. https://doi.org/10.3390/s26030855. The authors report **Pearson's r > 0.99 between the Polar H10 and a gold-standard ECG system for individual heart rate, both in aggregate and moment-to-moment**, and **Pearson's r > 0.95 for dyadic heart-rate synchrony** across multiple analytical approaches. The paper is the right external anchor for any "our pipeline matches Kubios / matches a gold-standard ECG" claim this project might eventually want to make: Chung et al. 2026 already did the ground-truth work, and the Polar-Emotibit Analyzer only needs to reproduce *their* pipeline on *their* data to demonstrate parity.

**3. Wearipedia Polar H10 notebook.** I flagged this already in the earlier audit. It is *instructional*, not a dataset — it walks the reader through extracting HR and RR intervals from the Polar Accesslink cloud API. It bundles no CSVs. It is useful only if a student already has their own Polar H10 + a Polar Flow account and wants a working Python recipe; it is not useful for the smoke-test pipeline run.

## Why the OSF dataset changes the plan

The integration plan from earlier today assumed the smoke test would have to work with *mismatched* public data — a Polar H10 session from `iitis/Polar-HRV-data-analysis` paired with an EmotiBit session from `gmaione1098/EmotiData`, recorded on different dates by different people. That plan produces a smoke test whose *expected* sync-QC verdict is `no_go`/red (no temporal overlap), which is useful as a negative test but not as a positive one. With the Chung et al. dataset, the smoke test instead runs against a Polar H10 session that has a paired gold-standard ECG — so the positive test case is **reproduce Chung et al.'s r > 0.99 HR correspondence on their data**. That is a more honest and more rigorous endpoint than "the pipeline runs without throwing."

The paired gold-standard ECG is also load-bearing for the Kubios-parity ambition in the newer repo's README. Kubios is itself validated against ECG; if the Polar-Emotibit Analyzer matches the Polar H10's RR-derived HRV against the gold-standard ECG's HRV on Chung et al.'s data, it has done the *exact* piece of work that `docs/REAL_DATA_SYNC_COLLECTION_REPORT_2026-03-01.md` in the sibling repo lists as "still mandatory for external claims". One dataset, one commit cycle, one of the sibling's four outstanding mandatory items closed.

There is one caveat. The OSF dataset does **not** contain EmotiBit recordings — it is Polar H10 plus gold-standard ECG, not Polar H10 plus EmotiBit EDA. So the smoke test against Chung et al. data validates the *HRV half* of the pipeline; the *EDA half* still needs a matching-session EmotiBit source, and for that the `gmaione1098/EmotiData` repo remains the best public option. The full end-to-end test (Polar + EmotiBit paired on the same wrist in the same sitting) still requires a real hardware collection, which is the 160sp lab task you already own.

## Bonus: Bleakheart is the BLE stack the sibling repo is missing

The Chung et al. acquisition pipeline uses **Bleakheart**, a BLE library specifically targeted at the Polar H10, built on top of the cross-platform `bleak` BLE library that the sibling's `docs/GAP_ANALYSIS_POTEMKIN_2026-03-02.md` flagged as `❌ 0%` complete. If the project ever moves past its file-only post-hoc scope and wants to do actual device integration, Bleakheart is very likely the right dependency rather than writing BLE handling from scratch. The sibling's gap analysis estimated 4–6 weeks for the device-integration phase with a team; a Bleakheart-plus-`bleak` adoption probably halves that for the Polar half alone. Worth recording even though it is out of scope for this week's work.

## Adjusted Path-A smoke-test step

Replacing the last step of the integration plan's `§ 4`:

```bash
# Step 6 (updated): smoke-test against Chung et al. (2026) OSF dataset.
mkdir -p data/samples
cd data/samples

# The OSF dataset lives at https://osf.io/wym3s/.  Download one participant's
# ECG + IBI files using either the web UI or the osfclient CLI:
#   pip install osfclient --break-system-packages
#   osf -p wym3s clone .
# The dataset is structured one-folder-per-participant; pick a single
# representative participant (e.g. P01) for the first smoke test.

# Column rename: the Chung et al. format carries (timestamp_ns, ecg_uv) for
# raw ECG at 133 Hz.  Our pipeline expects (timestamp_ms, hr_bpm, rr_ms).
# The IBI file already carries RR intervals; convert timestamps ns -> ms,
# derive hr_bpm = 60000/rr_ms per beat, emit as polar_sample_01.csv.

python3 scripts/chung2026_to_polar_schema.py \
    --participant-dir data/samples/P01 \
    --out data/samples/polar_sample_01.csv

# Run the pipeline (POST the CSV through the /api/v1/analyze endpoint)
# and compare the computed HR series against the gold-standard ECG-derived
# HR from the same participant.  Expected: Pearson r > 0.99 per the
# Chung et al. published finding.

curl -F "polar_file=@data/samples/polar_sample_01.csv" \
     -F "emotibit_file=@data/synthetic/emotibit_synthetic.csv" \
     http://localhost:8000/api/v1/analyze | jq .
```

Write `docs/SAMPLE_DATA_SMOKE_TEST_2026-04-20.md` with the result row and the computed correspondence against the paired gold-standard ECG in the same folder. If the correspondence falls below Chung et al.'s r > 0.99 threshold, that is a regression to investigate — either in the RR extraction, the ectopic filter, or the drift-correction arithmetic.

## Other Polar H10 datasets worth knowing about

The web search surfaced three datasets on Figshare labelled `ecg-polar-h10-set2`, `ecg-polar-h10-set4`, and `ecg-polar-h10-set7`, plus a cyclist-worn ECG corpus on Zenodo labelled `ECGSWS`. I did not need them once the Chung et al. OSF dataset surfaced, but they exist if a larger validation corpus is ever wanted. Figshare URLs:

- https://figshare.com/articles/dataset/ecg-polar-h10-set2/14461757
- https://figshare.com/articles/dataset/ecg-polar-h10-set4/16778962
- https://figshare.com/articles/dataset/ecg-polar-h10-set7/20081294

## References

Chung, V., Chopin, L., Karadayi, J., & Grèzes, J. (2026). Validity of the Polar H10 for continuous measures of heart rate and heart rate synchrony analysis. *Sensors, 26*(3), 855. https://doi.org/10.3390/s26030855 — OSF data deposit at https://doi.org/10.17605/OSF.IO/WYM3S.

Gilfriche, P., Liénard, J.-B., Deschodt-Arsac, V., Arsac, L. M., Aubert, A. E., & Deschodt, V. (2022). Validity of the Polar H10 sensor for heart rate variability analysis during resting state and incremental exercise in recreational men and women. *Sensors, 22*(17), 6536. https://doi.org/10.3390/s22176536 — the prior-art validation paper that Chung et al. replicate and extend. Google cites ≈ 200.

## Sources

- [OSF project WYM3S (Chung et al. 2026 data)](https://osf.io/wym3s/overview)
- [PMC article — Chung et al. 2026](https://pmc.ncbi.nlm.nih.gov/articles/PMC12899868/)
- [MDPI publisher page for Chung et al. 2026](https://www.mdpi.com/1424-8220/26/3/855)
- [Wearipedia Polar H10 notebook](https://wearipedia.readthedocs.io/en/latest/notebooks/polar_h10.html)
- [Bleakheart BLE library (Polar H10 via bleak)](https://github.com/scipionox/bleakheart) *(the Chung et al. acquisition stack)*
- [osfclient — Python CLI for downloading OSF projects](https://github.com/osfclient/osfclient)
- [ecg-polar-h10-set2 on Figshare](https://figshare.com/articles/dataset/ecg-polar-h10-set2/14461757)
- [ecg-polar-h10-set4 on Figshare](https://figshare.com/articles/dataset/ecg-polar-h10-set4/16778962)
- [ecg-polar-h10-set7 on Figshare](https://figshare.com/articles/dataset/ecg-polar-h10-set7/20081294)
