# myfinmodel

Python app for modeling retirement spending and stress testing.

## Development

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the Streamlit app:

```bash
streamlit run app.py
```

Run tests:

```bash
python -m pytest tests/ -v
```

## Portable folder distribution (zip, no installer)

Portable packaging assets are located in:

- `packaging/launcher/`
- `packaging/launch_myfinmodel.bat`
- `packaging/myfinmodel.spec`
- `packaging/build_portable.ps1`

On Windows, build a portable zip artifact with:

```powershell
./packaging/build_portable.ps1 -Version "0.1.0"
```

Output artifact:

- `dist/MyFinModel-vX.Y.Z-portable.zip`
