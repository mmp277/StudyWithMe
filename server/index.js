import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";
import express from "express";
import multer from "multer";
import cors from "cors";
import morgan from "morgan";
import { spawn } from "child_process";
import { nanoid } from "nanoid";
import mongoose from "mongoose";
import cookieParser from "cookie-parser";
import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
// removed nodemailer due to OTP removal

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const ROOT = path.resolve(__dirname, "..");
const PROJECT_ROOT = path.resolve(__dirname, "..");
const INPUTS_DIR = path.join(PROJECT_ROOT, "inputs");
const OUTPUTS_DIR = path.join(PROJECT_ROOT, "outputs");
const WEB_DIR = path.join(PROJECT_ROOT, "web");

fs.mkdirSync(INPUTS_DIR, { recursive: true });
fs.mkdirSync(OUTPUTS_DIR, { recursive: true });
fs.mkdirSync(WEB_DIR, { recursive: true });

// Minimal .env loader (avoids external dependency)
try {
  const envPath = path.join(PROJECT_ROOT, ".env");
  if (fs.existsSync(envPath)) {
    const content = fs.readFileSync(envPath, "utf8");
    for (const line of content.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const idx = trimmed.indexOf("=");
      if (idx === -1) continue;
      const key = trimmed.slice(0, idx).trim();
      const valRaw = trimmed.slice(idx + 1).trim();
      const val = valRaw.replace(/^"|"$/g, '').replace(/^'|'$/g, '');
      if (!(key in process.env)) process.env[key] = val;
    }
  }
} catch {
  // ignore env loading errors
}
const app = express();
// Enable credentials; reflect origin for CORS
app.use(cors({
  origin: (origin, cb) => cb(null, true),
  credentials: true,
}));
app.use(morgan("dev"));
app.use(express.json());
app.use(cookieParser());

// Static frontend
// Serve static with no-store to avoid cached old JS interfering
app.use(express.static(WEB_DIR, { setHeaders: (res) => { res.set("Cache-Control", "no-store"); }}));

function emptyDirectory(dirPath) {
  try {
    if (!fs.existsSync(dirPath)) return;
    for (const entry of fs.readdirSync(dirPath)) {
      const full = path.join(dirPath, entry);
      const stat = fs.statSync(full);
      if (stat.isDirectory()) {
        emptyDirectory(full);
        fs.rmdirSync(full, { recursive: true });
      } else {
        fs.unlinkSync(full);
      }
    }
  } catch {}
}

// MongoDB connection
const MONGODB_URI = process.env.MONGODB_URI || "";
if (MONGODB_URI) {
  mongoose.connect(MONGODB_URI).then(() => {
    // eslint-disable-next-line no-console
    console.log("MongoDB connected");
  }).catch((err) => {
    // eslint-disable-next-line no-console
    console.error("MongoDB connection error", err.message);
  });
} else {
  // eslint-disable-next-line no-console
  console.warn("MONGODB_URI not set. Auth features will not work.");
}

// Models
const userSchema = new mongoose.Schema({
  name: { type: String, trim: true },
  email: { type: String, required: true, unique: true, lowercase: true, index: true },
  passwordHash: { type: String, required: true },
  verified: { type: Boolean, default: true },
}, { timestamps: true });

const historySchema = new mongoose.Schema({
  userId: { type: mongoose.Schema.Types.ObjectId, ref: "User", index: true },
  action: { type: String, required: true },
  details: { type: String },
  files: { type: [String], default: [] },
  timestamp: { type: Date, default: () => new Date() },
}, { versionKey: false });

const User = mongoose.models.User || mongoose.model("User", userSchema);
const History = mongoose.models.History || mongoose.model("History", historySchema);

// Auth helpers
const JWT_SECRET = process.env.JWT_SECRET || "dev_secret_change_me";
function signToken(user) {
  return jwt.sign({ uid: user._id, email: user.email }, JWT_SECRET, { expiresIn: "7d" });
}
function authRequired(req, res, next) {
  const token = req.cookies?.token || "";
  try {
    if (!token) return res.status(401).json({ error: "Not authenticated" });
    const payload = jwt.verify(token, JWT_SECRET);
    req.auth = { userId: payload.uid, email: payload.email };
    next();
  } catch {
    return res.status(401).json({ error: "Invalid token" });
  }
}

// Best-effort auth: attaches req.auth if a valid cookie token exists, otherwise proceeds
function attachAuthIfPresent(req, _res, next) {
  const token = req.cookies?.token || "";
  if (!token) return next();
  try {
    const payload = jwt.verify(token, JWT_SECRET);
    req.auth = { userId: payload.uid, email: payload.email };
  } catch {}
  next();
}

async function recordHistory(userId, action, details, files) {
  try {
    if (!userId || !mongoose.connection.readyState) return;
    await History.create({ userId, action, details, files: Array.isArray(files) ? files : [] });
  } catch {}
}

// OTP removed: no mail transport

// Auth routes
app.post("/api/auth/register", async (req, res) => {
  try {
    const { name, email, password } = req.body || {};
    if (!email || !password) return res.status(400).json({ error: "Email and password required" });
    if (!mongoose.connection.readyState) return res.status(503).json({ error: "Database not connected" });
    const existing = await User.findOne({ email });
    if (existing) return res.status(409).json({ error: "Email already registered" });
    const passwordHash = await bcrypt.hash(password, 10);
    const user = await User.create({ name: name || "", email, passwordHash, verified: true });
    // Auto-login after register
    const token = signToken(user);
    res.cookie("token", token, { httpOnly: true, sameSite: "lax", secure: false, path: "/", maxAge: 7*24*60*60*1000 });
    return res.json({ ok: true });
  } catch (e) {
    return res.status(500).json({ error: "Register failed" });
  }
});

// OTP endpoints removed

app.post("/api/auth/login", async (req, res) => {
  try {
    const { email, password } = req.body || {};
    if (!email || !password) return res.status(400).json({ error: "Email and password required" });
    if (!mongoose.connection.readyState) return res.status(503).json({ error: "Database not connected" });
    const user = await User.findOne({ email });
    if (!user) return res.status(401).json({ error: "Invalid credentials" });
    const ok = await bcrypt.compare(password, user.passwordHash);
    if (!ok) return res.status(401).json({ error: "Invalid credentials" });
    // No email verification required
    const token = signToken(user);
    res.cookie("token", token, { httpOnly: true, sameSite: "lax", secure: false, path: "/", maxAge: 7*24*60*60*1000 });
    return res.json({ ok: true });
  } catch {
    return res.status(500).json({ error: "Login failed" });
  }
});

app.post("/api/auth/logout", (req, res) => {
  res.clearCookie("token", { path: "/" });
  return res.json({ ok: true });
});

app.get("/api/me", authRequired, async (req, res) => {
  try {
    const user = await User.findById(req.auth.userId).select("name email verified").lean();
    return res.json({ ok: true, user });
  } catch {
    return res.status(500).json({ error: "Failed" });
  }
});

// Storage per job
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const dest = req.uploadDest || INPUTS_DIR;
    fs.mkdirSync(dest, { recursive: true });
    cb(null, dest);
  },
  filename: (req, file, cb) => {
    cb(null, file.originalname);
  },
});

const upload = multer({ storage });

// Single-run: upload files directly to inputs/
app.post("/api/upload", attachAuthIfPresent, (req, res, next) => {
  // Clear previous inputs to avoid mixing
  emptyDirectory(INPUTS_DIR);
  // Also clear previous outputs so previews don't show stale data
  emptyDirectory(OUTPUTS_DIR);
  req.uploadDest = INPUTS_DIR;
  next();
}, upload.array("files", 50), (req, res) => {
  res.json({ uploaded: (req.files || []).map(f => ({ name: f.originalname, size: f.size })) });
});

// Trigger processing for current inputs -> outputs
app.post("/api/run", attachAuthIfPresent, async (req, res) => {
  const inputDir = INPUTS_DIR;
  const outDir = OUTPUTS_DIR;

  if (!fs.existsSync(inputDir) || fs.readdirSync(inputDir).length === 0) {
    return res.status(400).json({ error: "No uploaded files in inputs/" });
  }

  const candidates = [];
  // Prefer local venv python if present
  const venvWin = path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe");
  const venvNix = path.join(PROJECT_ROOT, ".venv", "bin", "python");
  if (fs.existsSync(venvWin)) candidates.push(venvWin);
  if (fs.existsSync(venvNix)) candidates.push(venvNix);
  if (process.env.PYTHON_EXEC && process.env.PYTHON_EXEC.trim()) candidates.push(process.env.PYTHON_EXEC.trim());
  if (process.platform === "win32") candidates.push("py");
  candidates.push("python");
  candidates.push("python3");

  const cliModule = "-m";
  const modulePath = "src.agent.cli";

  let responded = false;
  const tryNext = (idx) => {
    if (idx >= candidates.length) {
      if (!responded) {
        responded = true;
        return res.status(500).json({ error: "Python not found. Set PYTHON_EXEC in .env or ensure python is on PATH." });
      }
      return;
    }
    const exe = candidates[idx];
    const args = [cliModule, modulePath, inputDir, "--out", outDir];
    const child = spawn(exe, args, {
      cwd: PROJECT_ROOT,
      env: process.env,
      shell: false,
    });
    let logs = "";
    let started = false;
    logs += `[INFO] Trying Python: ${exe} ${args.join(" ")}\n`;
    child.stdout.on("data", (d) => { started = true; logs += d.toString(); });
    child.stderr.on("data", (d) => { started = true; logs += d.toString(); });
    child.on("error", () => {
      if (!started) return tryNext(idx + 1);
      if (!responded) { responded = true; res.status(500).json({ error: "Python spawn error", logs }); }
    });
    child.on("close", (code) => {
      if (!responded) {
        const ok = code === 0;
        responded = true;
        // Also report whether outputs exist
        const files = fs.readdirSync(outDir).filter(n => n.toLowerCase().endsWith('.docx'));
        const sum = path.join(outDir, "summaries.docx");
        const fc = path.join(outDir, "flashcards.docx");
        const fsheet = path.join(outDir, "formula_sheet.docx");
        // record per-user history if authenticated
        const authedUserId = req.auth?.userId;
        if (ok && authedUserId) {
          recordHistory(authedUserId, "AI processing completed", `Files: ${files.length}`, files);
        }
        res.json({ ok, code, logs, files, legacy: {
          summaries: fs.existsSync(sum),
          flashcards: fs.existsSync(fc),
          formula_sheet: fs.existsSync(fsheet),
        }, outputs: {
          summary: `/api/download/summaries.docx`,
          flashcards: `/api/download/flashcards.docx`,
          formulas: `/api/download/formula_sheet.docx`,
          preview: `/api/summary-preview`,
        }});
      }
    });
  };
  tryNext(0);
});

// Download any .docx in outputs (safe filename only)
app.get("/api/download/:name", (req, res) => {
  const { name } = req.params;
  const safe = /^[A-Za-z0-9_.-]+\.docx$/;
  if (!safe.test(name)) return res.status(400).send("Invalid file");
  const filePath = path.join(OUTPUTS_DIR, name);
  if (!fs.existsSync(filePath)) return res.status(404).send("Not found");
  res.download(filePath, name);
});

// Very light HTML preview from summaries.docx
import AdmZip from "adm-zip";
app.get("/api/summary-preview", async (req, res) => {
  const f = (req.query.file || "").toString();
  const docxPath = path.join(OUTPUTS_DIR, f && f.endsWith('.docx') ? f : "summaries.docx");
  if (!fs.existsSync(docxPath)) return res.status(404).json({ error: "No summary" });
  // Parse docx minimally: read document.xml and strip tags for a simple preview
  try {
    res.set("Cache-Control", "no-store");
    const zip = new AdmZip(docxPath);
    const entry = zip.getEntry("word/document.xml");
    const xml = entry ? zip.readAsText(entry) : "";
    // naive extraction of text inside <w:t>
    let texts = Array.from(xml.matchAll(/<w:t[^>]*>(.*?)<\/w:t>/g)).map(m => m[1]);
    // filter out file path-like headings
    const pathLike = /(?:[A-Za-z]:\\|\\\\|\/)\S+\.(?:pdf|txt|docx)$/i;
    texts = texts.filter(t => !pathLike.test(t));
    const html = texts.map(t => `<p>${t}</p>`).join("");
    res.type("html").send(`<div>${html}</div>`);
  } catch (e) {
    res.status(500).json({ error: "Failed to parse docx" });
  }
});

app.get("/api/flashcards-preview", async (req, res) => {
  const f = (req.query.file || "").toString();
  const docxPath = path.join(OUTPUTS_DIR, f && f.endsWith('.docx') ? f : "flashcards.docx");
  if (!fs.existsSync(docxPath)) return res.status(404).json({ error: "No flashcards" });
  try {
    res.set("Cache-Control", "no-store");
    const zip = new AdmZip(docxPath);
    const entry = zip.getEntry("word/document.xml");
    const xml = entry ? zip.readAsText(entry) : "";
    let texts = Array.from(xml.matchAll(/<w:t[^>]*>(.*?)<\/w:t>/g)).map(m => m[1]);
    const pathLike = /(?:[A-Za-z]:\\|\\\\|\/)\S+\.(?:pdf|txt|docx)$/i;
    texts = texts.filter(t => !pathLike.test(t));
    const html = texts.map(t => `<p>${t}</p>`).join("");
    res.type("html").send(`<div>${html}</div>`);
  } catch (e) {
    res.status(500).json({ error: "Failed to parse docx" });
  }
});

// Flashcards as JSON (Q/A pairs)
app.get("/api/flashcards-json", async (req, res) => {
  const f = (req.query.file || "").toString();
  const docxPath = path.join(OUTPUTS_DIR, f && f.endsWith('.docx') ? f : "flashcards.docx");
  if (!fs.existsSync(docxPath)) return res.status(404).json({ error: "No flashcards" });
  try {
    res.set("Cache-Control", "no-store");
    const zip = new AdmZip(docxPath);
    const entry = zip.getEntry("word/document.xml");
    const xml = entry ? zip.readAsText(entry) : "";
    let texts = Array.from(xml.matchAll(/<w:t[^>]*>(.*?)<\/w:t>/g)).map(m => m[1]);
    const pathLike = /(?:[A-Za-z]:\\|\\\\|\/)\S+\.(?:pdf|txt|docx)$/i;
    texts = texts.map(t=>t.trim()).filter(t => t && !pathLike.test(t));

    // Heuristic: parse Q:/A: or pair consecutive lines
    const cards = [];
    let currentQ = null;
    for (const line of texts) {
      const qMatch = line.match(/^\s*(?:Q\s*[:\-]\s*|Question\s*[:\-]\s*)(.+)$/i);
      const aMatch = line.match(/^\s*(?:A\s*[:\-]\s*|Answer\s*[:\-]\s*)(.+)$/i);
      if (qMatch) {
        if (currentQ) { cards.push({ q: currentQ, a: "" }); }
        currentQ = qMatch[1].trim();
        continue;
      }
      if (aMatch) {
        const ans = aMatch[1].trim();
        if (currentQ) { cards.push({ q: currentQ, a: ans }); currentQ = null; }
        continue;
      }
      // fallback: accumulate pairs
      if (currentQ === null) {
        currentQ = line;
      } else {
        cards.push({ q: currentQ, a: line });
        currentQ = null;
      }
    }
    if (currentQ) { cards.push({ q: currentQ, a: "" }); }
    // Drop leading non-QA header-like card if present
    if (cards.length) {
      const first = cards[0];
      const looksHeader = (!first.a || first.a.trim().length === 0) ||
        (first.q && first.q.split(/\s+/).length < 3) ||
        /^(?:flashcards?|summary|contents?|study)/i.test(first.q || "");
      if (looksHeader) cards.shift();
    }
    // Normalize: remove starting labels like "Q:", "Q8.", "A:", "A8.)"
    const stripLabel = (s) => {
      if (!s) return s;
      return s
        .replace(/^\s*(?:Q|Question)\s*\d*\s*[:.)-]?\s*/i, "")
        .replace(/^\s*(?:A|Answer)\s*\d*\s*[:.)-]?\s*/i, "")
        .replace(/^\s*[•\-]\s*/, "")
        .trim();
    };
    for (const c of cards) {
      c.q = stripLabel(c.q);
      c.a = stripLabel(c.a);
    }
    return res.json({ ok: true, cards });
  } catch (e) {
    return res.status(500).json({ error: "Failed to parse flashcards" });
  }
});

app.get("/api/formulas-preview", async (req, res) => {
  const f = (req.query.file || "").toString();
  const docxPath = path.join(OUTPUTS_DIR, f && f.endsWith('.docx') ? f : "formula_sheet.docx");
  if (!fs.existsSync(docxPath)) return res.status(404).json({ error: "No formula sheet" });
  try {
    res.set("Cache-Control", "no-store");
    const zip = new AdmZip(docxPath);
    const entry = zip.getEntry("word/document.xml");
    const xml = entry ? zip.readAsText(entry) : "";
    let texts = Array.from(xml.matchAll(/<w:t[^>]*>(.*?)<\/w:t>/g)).map(m => m[1]);
    const pathLike = /(?:[A-Za-z]:\\|\\\\|\/)\S+\.(?:pdf|txt|docx)$/i;
    texts = texts.filter(t => !pathLike.test(t));
    const html = texts.map(t => `<p>${t}</p>`).join("");
    res.type("html").send(`<div>${html}</div>`);
  } catch (e) {
    res.status(500).json({ error: "Failed to parse docx" });
  }
});

// Health
app.get("/api/health", (req, res) => res.json({ ok: true }));

// Public config for frontend
app.get("/api/config", (req, res) => {
  res.json({
    github: process.env.GITHUB || "",
  });
});

// User history endpoint
app.get("/api/history", authRequired, async (req, res) => {
  try {
    const page = Math.max(1, parseInt((req.query.page || "1"), 10));
    const limit = Math.min(50, Math.max(1, parseInt((req.query.limit || "10"), 10)));
    const skip = (page - 1) * limit;
    const [items, total] = await Promise.all([
      History.find({ userId: req.auth.userId }).sort({ timestamp: -1 }).skip(skip).limit(limit).lean(),
      History.countDocuments({ userId: req.auth.userId }),
    ]);
    res.json({ ok: true, items, page, limit, total });
  } catch {
    res.status(500).json({ error: "Failed to load history" });
  }
});

// Clear history for current user
app.delete("/api/history", authRequired, async (req, res) => {
  try {
    await History.deleteMany({ userId: req.auth.userId });
    res.json({ ok: true });
  } catch {
    res.status(500).json({ error: "Failed to clear history" });
  }
});

// Reset inputs and outputs (to avoid stale previews across refreshes)
app.post("/api/reset", (req, res) => {
  emptyDirectory(INPUTS_DIR);
  emptyDirectory(OUTPUTS_DIR);
  res.json({ ok: true });
});

function startServer(basePort, attemptsLeft){
  const port = basePort;
  const server = app.listen(port, () => {
    // eslint-disable-next-line no-console
    console.log(`Server listening on http://localhost:${port}`);
  });
  server.on('error', (err) => {
    if (err && err.code === 'EADDRINUSE' && attemptsLeft > 0) {
      const nextPort = port + 1;
      // eslint-disable-next-line no-console
      console.warn(`Port ${port} in use, trying ${nextPort}...`);
      startServer(nextPort, attemptsLeft - 1);
    } else {
      throw err;
    }
  });
}

const START_PORT = Number(process.env.PORT || 3000);
startServer(START_PORT, 10);


