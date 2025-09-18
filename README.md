


### Name : Mithil Modi
### Institute : Indian Institute of Technology, Guwahati
### Department : Mechanical Engineering



# AI Lecture Agent (Gemini-powered)

Read lecture notes (.pdf, .txt, .docx), summarize with Gemini, generate flashcards, and extract a formula sheet into Word documents. Only the input directory is required.

## Requirements
- Python 3.9+

## Install
```powershell
cd StudyWithMe
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configure API key
Create a `.env` file in the project root or set the env var in the shell:
```
GEMINI_API_KEY=<your_key>
```
Or in PowerShell for the current session:
```powershell
$env:GEMINI_API_KEY = "<your_key>"
```

## Run
```powershell
python -m src.agent.cli "C:\path\to\lecture_notes" --out outputs
```
Outputs: `outputs\summaries.docx`, `outputs\flashcards.docx`, `outputs\formula_sheet.docx`.

## Notes
- Uses Gemini (`gemini-1.5-flash`) via `google-generativeai`. No paid libraries are required, but API usage may incur costs on your account.
- Formula extraction is heuristic. For scanned PDFs, add OCR if needed (e.g., Tesseract).

## Web app (Node.js frontend + backend)

### Demo Video
<video src="https://github.com/mmp277/StudyWithMe/releases/download/Demo/Demo.mp4" controls width="720"></video>

### Setup
```powershell
# In project root
npm install
```

Ensure Python env is available and dependencies installed as above. The server will call:
```powershell
python -m src.agent.cli <input_dir> --out <outputs_dir>
```
If your Python is not `python`, set:
```powershell
$env:PYTHON_EXEC = "C:\\path\\to\\python.exe"
```

Also set your Gemini key for the Python process:
```powershell
$env:GEMINI_API_KEY = "<your_key>"
```

### Run
```powershell
npm run start
# Open http://localhost:3000
```

### Usage
- Click "Create new job"
- Upload .pdf/.txt/.docx files
- Click "Process" to run the agent
- Download generated `summaries.docx`, `flashcards.docx`, `formula_sheet.docx`
- A simple summary preview is rendered on the page
