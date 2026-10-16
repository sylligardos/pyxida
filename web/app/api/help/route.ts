import { NextResponse } from "next/server";
import { CITES, HELP } from "@/lib/help";

// The help text, for the Needle screens (public/play reads it at /api/help).
export const GET = () => NextResponse.json({ help: HELP, cites: CITES });
