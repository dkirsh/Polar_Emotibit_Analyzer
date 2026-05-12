### Polar_Emotibit_Analyzer GitHub push — 2026-04-21

- Remote URL added: https://github.com/dkirsh/Polar_Emotibit_Analyzer.git
- Initial push result: remote was not empty; GitHub contained a LICENSE-only initial commit (`53f5bae`), so I ran `git fetch origin`, merged with `git merge --allow-unrelated-histories origin/main`, and then pushed `main` successfully.
- Final origin/main SHA: `dca19890da73005ff674caf0c806df8747e329df` (the README URL-fix commit on top of the unrelated-histories merge).
- Visibility, default branch, pushed-at timestamp from `gh repo view`: `PUBLIC`, `main`, `2026-04-22T23:30:38Z`.
- Any deviation from this prompt and why: the remote was not empty, so `origin/main` after the initial publish was the merge commit `5d44224438eee1e39eb3eceb09cf142016a5bc49` rather than `2fdfeba`; after the required README fix commit, the final remote SHA became `dca19890da73005ff674caf0c806df8747e329df`.

### CW structural cleanup — 2026-04-22

- Commit A (archive): `61323ecc79ed8a051b226a793f234bd3d88668b7` "Archive 2026-04-20 working docs under docs/archive/2026-04-20/"
- Commit B (contracts+index+changelog): `ddd00a77b3b41145e89cbcc6942cac2ffcd31c58` "Add contracts/ with six module contracts; docs index; CHANGELOG"
- Pre-pytest: 23/2/0
- Post-pytest: 23/2/0
- TS + vite build: clean
- Push result: fast-forward onto `dca1989`
- Final origin/main SHA: `ddd00a77b3b41145e89cbcc6942cac2ffcd31c58`
- Any deviations: the two target commits were already present locally on the Mac, so there was nothing to reconstruct from appendices; backend pytest did not match the prompt's expected 25/0/0 because the current `python3` environment is missing declared dependencies `openpyxl` and `reportlab`, but the pre/post results matched exactly and the two commits are docs-only with no code-path changes.

### Backend dependency install failure — 2026-04-22

- Diagnostic import check in `backend/.venv` failed as expected with `ModuleNotFoundError: No module named 'reportlab'`.
- Attempted remediation command: `.venv/bin/python -m pip install -e '.[dev]'`
- Result: install failed before dependency resolution because setuptools rejected `backend/pyproject.toml` reading `../README.md` from outside the backend project root.

Full traceback:

```text
Getting requirements to build editable: finished with status 'error'
error: subprocess-exited-with-error

× Getting requirements to build editable did not run successfully.
│ exit code: 1
╰─> [58 lines of output]
    Traceback (most recent call last):
      File "/Users/davidusa/REPOS/Polar_Emotibit_Analyzer/backend/.venv/lib/python3.14/site-packages/pip/_vendor/pyproject_hooks/_in_process/_in_process.py", line 389, in <module>
        main()
        ~~~~^^
      File "/Users/davidusa/REPOS/Polar_Emotibit_Analyzer/backend/.venv/lib/python3.14/site-packages/pip/_vendor/pyproject_hooks/_in_process/_in_process.py", line 373, in main
        json_out["return_val"] = hook(**hook_input["kwargs"])
                                 ~~~~^^^^^^^^^^^^^^^^^^^^^^^^
      File "/Users/davidusa/REPOS/Polar_Emotibit_Analyzer/backend/.venv/lib/python3.14/site-packages/pip/_vendor/pyproject_hooks/_in_process/_in_process.py", line 157, in get_requires_for_build_editable
        return hook(config_settings)
      File "/private/var/folders/0j/kpfv_dq96mx0lr8jc744nhrh0000gn/T/pip-build-env-1_nkg35a/overlay/lib/python3.14/site-packages/setuptools/build_meta.py", line 481, in get_requires_for_build_editable
        return self.get_requires_for_build_wheel(config_settings)
               ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^
      File "/private/var/folders/0j/kpfv_dq96mx0lr8jc744nhrh0000gn/T/pip-build-env-1_nkg35a/overlay/lib/python3.14/site-packages/setuptools/build_meta.py", line 333, in get_requires_for_build_wheel
        return self._get_build_requires(config_settings, requirements=[])
               ~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
      File "/private/var/folders/0j/kpfv_dq96mx0lr8jc744nhrh0000gn/T/pip-build-env-1_nkg35a/overlay/lib/python3.14/site-packages/setuptools/build_meta.py", line 301, in _get_build_requires
        self.run_setup()
        ~~~~~~~~~~~~~~^^
      File "/private/var/folders/0j/kpfv_dq96mx0lr8jc744nhrh0000gn/T/pip-build-env-1_nkg35a/overlay/lib/python3.14/site-packages/setuptools/build_meta.py", line 317, in run_setup
        exec(code, locals())
        ~~~~^^^^^^^^^^^^^^^^
      File "<string>", line 1, in <module>
      File "/private/var/folders/0j/kpfv_dq96mx0lr8jc744nhrh0000gn/T/pip-build-env-1_nkg35a/overlay/lib/python3.14/site-packages/setuptools/__init__.py", line 117, in setup
        return distutils.core.setup(**attrs)  # type: ignore[return-value]
               ~~~~~~~~~~~~~~~~~~~~^^^^^^^^^
      File "/private/var/folders/0j/kpfv_dq96mx0lr8jc744nhrh0000gn/T/pip-build-env-1_nkg35a/overlay/lib/python3.14/site-packages/setuptools/_distutils/core.py", line 160, in setup
        dist.parse_config_files()
        ~~~~~~~~~~~~~~~~~~~~~~~^^
      File "/private/var/folders/0j/kpfv_dq96mx0lr8jc744nhrh0000gn/T/pip-build-env-1_nkg35a/overlay/lib/python3.14/site-packages/setuptools/dist.py", line 762, in parse_config_files
        pyprojecttoml.apply_configuration(self, filename, ignore_option_errors)
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
      File "/private/var/folders/0j/kpfv_dq96mx0lr8jc744nhrh0000gn/T/pip-build-env-1_nkg35a/overlay/lib/python3.14/site-packages/setuptools/config/pyprojecttoml.py", line 73, in apply_configuration
        return _apply(dist, config, filepath)
      File "/private/var/folders/0j/kpfv_dq96mx0lr8jc744nhrh0000gn/T/pip-build-env-1_nkg35a/overlay/lib/python3.14/site-packages/setuptools/config/_apply_pyprojecttoml.py", line 54, in apply
        _apply_project_table(dist, config, root_dir)
        ~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^
      File "/private/var/folders/0j/kpfv_dq96mx0lr8jc744nhrh0000gn/T/pip-build-env-1_nkg35a/overlay/lib/python3.14/site-packages/setuptools/config/_apply_pyprojecttoml.py", line 82, in _apply_project_table
        corresp(dist, value, root_dir)
        ~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^
      File "/private/var/folders/0j/kpfv_dq96mx0lr8jc744nhrh0000gn/T/pip-build-env-1_nkg35a/overlay/lib/python3.14/site-packages/setuptools/config/_apply_pyprojecttoml.py", line 184, in _long_description
        text = expand.read_files(file, root_dir)
      File "/private/var/folders/0j/kpfv_dq96mx0lr8jc744nhrh0000gn/T/pip-build-env-1_nkg35a/overlay/lib/python3.14/site-packages/setuptools/config/expand.py", line 126, in read_files
        return '\n'.join(
               ~~~~~~~~~^
            _read_file(path)
            ^^^^^^^^^^^^^^^^
            for path in _filter_existing_files(_filepaths)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
            if _assert_local(path, root_dir)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        )
        ^
      File "/private/var/folders/0j/kpfv_dq96mx0lr8jc744nhrh0000gn/T/pip-build-env-1_nkg35a/overlay/lib/python3.14/site-packages/setuptools/config/expand.py", line 129, in <genexpr>
        if _assert_local(path, root_dir)
           ~~~~~~~~~~~~~^^^^^^^^^^^^^^^^
      File "/private/var/folders/0j/kpfv_dq96mx0lr8jc744nhrh0000gn/T/pip-build-env-1_nkg35a/overlay/lib/python3.14/site-packages/setuptools/config/expand.py", line 149, in _assert_local
        raise DistutilsOptionError(msg)
    distutils.errors.DistutilsOptionError: Cannot access '/Users/davidusa/REPOS/Polar_Emotibit_Analyzer/backend/../README.md' (or anything outside '/Users/davidusa/REPOS/Polar_Emotibit_Analyzer/backend')
    [end of output]

note: This error originates from a subprocess, and is likely not a problem with pip.
ERROR: Failed to build 'file:///Users/davidusa/REPOS/Polar_Emotibit_Analyzer/backend' when getting requirements to build editable
```

### Near-term to do — 2026-05-02

- **Validate synchronization and event-mark correctness more directly**
  - Build a proper validation surface for whether Polar/EmotiBit alignment is not only numerically acceptable but semantically correct at event transitions.
  - Include event-level checks, not merely session-level drift and sync-QC aggregates.
  - The practical question is: are the claimed baseline/task/recovery or room-transition markers actually attached to the right physiological moments?

- **Support users who have no marker CSV with event timestamps**
  - Design a fallback workflow for users who know the session structure but do not possess a formal timestamp CSV.
  - This should likely include one or more of:
    - manual event entry,
    - approximate interval entry,
    - click-to-mark on a chart,
    - recovery of markers from notes or a simple text schedule.
  - The aim is to avoid the present all-or-nothing situation in which event-aware interpretation depends on a pre-existing CSV artifact.
