// Serves the exported data files to the browser. Locally they come from
// DATA_ROOT; online the client fetches the same paths from object storage.

import { promises as fs } from "fs";
import path from "path";
import { NextRequest } from "next/server";
import { DATA_ROOT } from "@/lib/data";

const TYPES: Record<string, string> = { ".json": "application/json", ".u16": "application/octet-stream" };

export async function GET(_req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const parts = (await params).path;
  if (parts.some((p) => p.includes("..") || p.startsWith("."))) return new Response("Bad path", { status: 400 });
  const file = path.join(DATA_ROOT, ...parts);
  try {
    const body = await fs.readFile(file);
    const type = TYPES[path.extname(file)] ?? "application/octet-stream";
    return new Response(new Uint8Array(body), { headers: { "content-type": type, "cache-control": "no-cache" } });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}
