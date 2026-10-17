import createClient from "openapi-fetch";

import { ENV } from "@/env";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type Location = Schemas["Location"];
export type Skill = Schemas["Skill"];
export type JobPosting = Schemas["JobPosting"];
export type PostingStatus = Schemas["PostingStatus"];
export type TimeSlot = Schemas["TimeSlot"];
export type PostingRequirement = Schemas["PostingRequirement"];
export type AuditCheck = Schemas["AuditCheck"];
export type YouthCreate = Schemas["YouthCreate"];
export type Youth = Schemas["Youth"];
export type ProfileSkill = Schemas["ProfileSkill"];
export type InterviewStep = Schemas["InterviewStep"];
export type AgentTrace = Schemas["AgentTrace"];
export type AgentName = AgentTrace["agent"];
export type AgentTraceKind = AgentTrace["kind"];
export type MatchResult = Schemas["MatchResult"];
export type MatchStatus = Schemas["MatchStatus"];
export type ScoreBreakdown = Schemas["ScoreBreakdown"];
export type ReviewTask = Schemas["ReviewTask"];
export type ReviewKind = Schemas["ReviewKind"];
export type ReviewStatus = Schemas["ReviewStatus"];
export type ReviewDecision = Schemas["ReviewDecision"];
export type Course = Schemas["Course"];
export type CourseSession = Schemas["CourseSession"];
export type TrainingPlan = Schemas["TrainingPlan"];
export type Problem = Schemas["Problem"];
export type Trace =
	paths["/traces/{threadId}"]["get"]["responses"][200]["content"]["application/json"];
export type TraceStatus = Trace["status"];
export type TraceSummary = Schemas["TraceSummary"];

/*
 * Este módulo también corre en el navegador (ingesta, perfil). En `next dev`,
 * varlock solo sustituye `ENV.*` en archivos "use client", así que aquí se
 * cae a `process.env.NEXT_PUBLIC_*`, que Next.js incrusta en el bundle.
 */
const PUBLIC_API_URL: string =
	ENV.NEXT_PUBLIC_API_URL ??
	process.env.NEXT_PUBLIC_API_URL ??
	"http://localhost:8000";

/** Base del contrato: `servers[0].url` en packages/api-spec/openapi.yaml. */
export const API_BASE_URL = `${PUBLIC_API_URL.replace(/\/+$/, "")}/api/v1`;

/** auto: mocks solo si la API falla · siempre: nunca llama a la API · nunca: muestra el error. */
export const MOCK_MODE: typeof ENV.NEXT_PUBLIC_API_MOCKS =
	ENV.NEXT_PUBLIC_API_MOCKS ??
	(process.env.NEXT_PUBLIC_API_MOCKS as
		| typeof ENV.NEXT_PUBLIC_API_MOCKS
		| undefined) ??
	"auto";

export const api = createClient<paths>({ baseUrl: API_BASE_URL });
