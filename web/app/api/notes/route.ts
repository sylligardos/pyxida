// The Workbench notes, kept in one JSON file in the repo (data/notes.json,
// git-ignored) so they outlive the browser. GET returns them all, PUT
// replaces them all: the file is small and one person writes it.

import { promises as fs } from "fs";
import path from "path";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const FILE = process.env.PYXIDA_NOTES ?? path.join(process.cwd(), "..", "data", "notes.json");

type Notes = Record<string, { note: string; updated: string }>;

async function read(): Promise<Notes> {
  try { return JSON.parse(await fs.readFile(FILE, "utf8")) as Notes; } catch { return {}; }
}

export async function GET() {
  return NextResponse.json(await read());
}

export async function PUT(req: Request) {
  const body = (await req.json().catch(() => null)) as Notes | null;
  if (!body || typeof body !== "object" || Array.isArray(body)) return NextResponse.json({ error: "expected an object of notes" }, { status: 400 });
  const notes: Notes = {};
  for (const [k, v] of Object.entries(body)) {
    if (v && typeof v.note === "string" && typeof v.updated === "string" && v.note.trim()) notes[k] = { note: v.note, updated: v.updated };
  }
  await fs.mkdir(path.dirname(FILE), { recursive: true });
  await fs.writeFile(FILE, JSON.stringify(notes, null, 2) + "\n", "utf8");
  return NextResponse.json(notes);
}
