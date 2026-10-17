/**
 * Operaciones que disparan agentes (H2), llamadas desde el navegador con el
 * cliente tipado. Si la API no existe o no implementa el endpoint
 * (sin respuesta, 404, 405 o 501) y NEXT_PUBLIC_API_MOCKS lo permite, caen a
 * `mock-agents.ts`. Los errores de negocio (422 guardrail, 413…) se muestran tal cual.
 */
import type { DataSource } from "./catalog";
import {
	type AgentTrace,
	API_BASE_URL,
	api,
	type InterviewStep,
	type JobPosting,
	MOCK_MODE,
	type Problem,
	type ProfileSkill,
	type TraceStatus,
	type Youth,
	type YouthCreate,
} from "./client";
import * as mock from "./mock-agents";

export type Result<T> =
	| { ok: true; data: T; source: DataSource; reason?: string }
	| { ok: false; message: string; problem?: Problem };

export type Attempt<T> =
	| { kind: "ok"; data: T }
	| { kind: "unavailable"; reason: string }
	| { kind: "error"; message: string; problem?: Problem };

type ApiCall<T> = (
	signal: AbortSignal,
) => Promise<{ data?: T; error?: unknown; response: Response }>;

const UNAVAILABLE = new Set([404, 405, 501]);
export const MOCK_ALWAYS = "Modo de datos de ejemplo activado.";

const GUARDRAIL_COPY: Record<NonNullable<Problem["guardrail"]>, string> = {
	inyeccion: "Detectamos instrucciones dirigidas al sistema y no las seguimos.",
	fuera_de_alcance: "La entrada no corresponde a lo que este paso procesa.",
	dato_absurdo: "Algún dato no es plausible. Revísalo e inténtalo de nuevo.",
	archivo_invalido:
		"El archivo no es válido. Usa PDF o texto (.txt) de hasta 5 MB.",
	pii: "La entrada contiene datos personales sensibles que no debemos guardar.",
};

function asProblem(error: unknown): Problem | undefined {
	if (error && typeof error === "object" && "title" in error) {
		return error as Problem;
	}
	return undefined;
}

export function describeProblem(problem: Problem | undefined, status: number) {
	if (problem?.guardrail) {
		return problem.detail ?? GUARDRAIL_COPY[problem.guardrail];
	}
	if (problem?.detail) return problem.detail;
	if (problem?.title) return problem.title;
	if (status === 413) return "El archivo supera el máximo de 5 MB.";
	if (status === 422) return "Algún dato no es válido. Revísalo.";
	return `La API respondió ${status}.`;
}

/**
 * Los agentes corren dentro de la petición HTTP con un presupuesto de LLM de
 * 45 s (LLM_BUDGET_S) más el solver y la BD: esperar menos aborta peticiones
 * que la API sí completa (la oferta queda creada y la web muestra un error).
 */
const AGENT_TIMEOUT_MS = 90_000;

export async function attempt<T>(
	call: ApiCall<T>,
	timeoutMs = AGENT_TIMEOUT_MS,
): Promise<Attempt<T>> {
	try {
		const { data, error, response } = await call(
			AbortSignal.timeout(timeoutMs),
		);
		if (response.ok && data !== undefined) return { kind: "ok", data };
		if (UNAVAILABLE.has(response.status)) {
			return {
				kind: "unavailable",
				reason: `La API respondió ${response.status} en ${API_BASE_URL}.`,
			};
		}
		const problem = asProblem(error);
		return {
			kind: "error",
			message: describeProblem(problem, response.status),
			problem,
		};
	} catch (err) {
		if (err instanceof DOMException && err.name === "TimeoutError") {
			return {
				kind: "error",
				message: "La API tardó demasiado en responder. Inténtalo de nuevo.",
			};
		}
		return {
			kind: "unavailable",
			reason: `La API no responde en ${API_BASE_URL}.`,
		};
	}
}

export async function runMock<T>(
	fn: () => Promise<T>,
	reason: string,
): Promise<Result<T>> {
	try {
		return { ok: true, data: await fn(), source: "mock", reason };
	} catch (err) {
		if (err instanceof mock.MockProblem) {
			return {
				ok: false,
				message: describeProblem(err.problem, err.problem.status),
				problem: err.problem,
			};
		}
		throw err;
	}
}

/** Llama a la API; si el endpoint no está disponible, usa el mock. */
export async function withMock<T>(
	call: ApiCall<T>,
	fallback: () => Promise<T>,
): Promise<Result<T>> {
	if (MOCK_MODE === "siempre") return runMock(fallback, MOCK_ALWAYS);
	const result = await attempt(call);
	if (result.kind === "ok")
		return { ok: true, data: result.data, source: "api" };
	if (result.kind === "error") {
		return { ok: false, message: result.message, problem: result.problem };
	}
	if (MOCK_MODE === "nunca") return { ok: false, message: result.reason };
	return runMock(fallback, result.reason);
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Espera a que el grafo termine. Devuelve null si `/traces` no está
 * disponible, para que el llamador sondee el recurso directamente.
 */
async function waitForTrace(
	threadId: string,
	{ timeoutMs = 60_000, intervalMs = 1200 } = {},
): Promise<{ status: TraceStatus; steps: AgentTrace[] } | null> {
	const deadline = Date.now() + timeoutMs;
	let misses = 0;
	let last: { status: TraceStatus; steps: AgentTrace[] } | null = null;
	while (Date.now() < deadline) {
		const r = await attempt(
			(signal) =>
				api.GET("/traces/{threadId}", {
					params: { path: { threadId } },
					signal,
				}),
			8000,
		);
		if (r.kind === "ok") {
			misses = 0;
			last = r.data;
			if (r.data.status !== "en_curso") return r.data;
		} else if (++misses >= 3) {
			return last;
		}
		await sleep(intervalMs);
	}
	return last;
}

// ---------------------------------------------------------------------------
// Jóvenes
// ---------------------------------------------------------------------------

export function createYouth(body: YouthCreate) {
	return withMock(
		(signal) => api.POST("/youth", { body, signal }),
		() => mock.createYouth(body),
	);
}

const MOCK_YOUTH =
	"Este perfil se creó con datos de ejemplo porque la API no respondía al registrarte.";
const MIXED_YOUTH =
	"Parte de las habilidades vienen de datos de ejemplo: el CV o la entrevista no estaban disponibles en la API.";

export async function getYouth(youthId: string): Promise<Result<Youth>> {
	const local = mock.getYouth(youthId);
	if (local)
		return { ok: true, data: local, source: "mock", reason: MOCK_YOUTH };

	const r = await attempt(
		(signal) =>
			api.GET("/youth/{youthId}", {
				params: { path: { youthId } },
				signal,
			}),
		10_000,
	);
	if (r.kind === "ok") {
		const extra = mock.overlay(youthId);
		if (extra.length === 0) return { ok: true, data: r.data, source: "api" };
		const seen = new Set(r.data.skills.map((s) => s.skill.id));
		return {
			ok: true,
			data: {
				...r.data,
				skills: [
					...r.data.skills,
					...extra.filter((s) => !seen.has(s.skill.id)),
				],
			},
			source: "mock",
			reason: MIXED_YOUTH,
		};
	}
	if (r.kind === "error")
		return { ok: false, message: r.message, problem: r.problem };
	return {
		ok: false,
		message: r.reason.includes("404")
			? "No encontramos este perfil. Puede que se haya creado en otra sesión."
			: r.reason,
	};
}

export type CvInput = { file?: File; text?: string };
export type CvOutcome = { youth: Youth; trace: AgentTrace[] | null };

export async function uploadCv(
	youthId: string,
	input: CvInput,
): Promise<Result<CvOutcome>> {
	const fromMock = async (reason: string) =>
		runMock(async () => {
			const { trace } = await mock.uploadCv(youthId, {
				text: input.text,
				fileName: input.file?.name,
			});
			const youth = mock.getYouth(youthId);
			if (youth) return { youth, trace };
			// Joven real con CV simulado: se relee de la API y se fusiona.
			const fresh = await getYouth(youthId);
			if (!fresh.ok) throw new Error(fresh.message);
			return { youth: fresh.data, trace };
		}, reason);

	if (mock.isMockYouth(youthId)) return fromMock(MOCK_YOUTH);
	if (MOCK_MODE === "siempre") return fromMock(MOCK_ALWAYS);

	const before = await getYouth(youthId);
	const initialCount = before.ok ? before.data.skills.length : 0;

	const form = new FormData();
	if (input.file) form.append("file", input.file);
	if (input.text) form.append("text", input.text);

	const r = await attempt(
		(signal) =>
			api.POST("/youth/{youthId}/cv", {
				params: { path: { youthId } },
				body: {},
				bodySerializer: () => form,
				signal,
			}),
		60_000,
	);
	if (r.kind === "error")
		return { ok: false, message: r.message, problem: r.problem };
	if (r.kind === "unavailable") {
		if (MOCK_MODE === "nunca") return { ok: false, message: r.reason };
		return fromMock(r.reason);
	}

	const trace = await waitForTrace(r.data.threadId);
	if (trace?.status === "error") {
		return { ok: false, message: "El agente de Perfil no pudo leer el CV." };
	}
	// Sin traza: sondea el perfil hasta que aparezcan habilidades nuevas.
	for (let i = 0; i < (trace ? 1 : 15); i++) {
		const youth = await getYouth(youthId);
		if (youth.ok && (trace || youth.data.skills.length > initialCount)) {
			return {
				ok: true,
				data: { youth: youth.data, trace: trace?.steps ?? null },
				source: youth.source,
				reason: youth.reason,
			};
		}
		await sleep(1500);
	}
	const youth = await getYouth(youthId);
	if (!youth.ok) return youth;
	return {
		ok: true,
		data: { youth: youth.data, trace: trace?.steps ?? null },
		source: "api",
	};
}

export function answerInterview(
	youthId: string,
	answer: string | null,
): Promise<Result<InterviewStep>> {
	if (
		mock.isMockYouth(youthId) ||
		(answer != null && mock.hasMockInterview(youthId))
	) {
		return runMock(
			() => mock.answerInterview(youthId, answer),
			mock.isMockYouth(youthId)
				? MOCK_YOUTH
				: "La entrevista sigue con datos de ejemplo porque la API no respondía al empezar.",
		);
	}
	return withMock(
		(signal) =>
			api.POST("/youth/{youthId}/interview", {
				params: { path: { youthId } },
				body: { answer },
				signal,
			}),
		() => mock.answerInterview(youthId, answer),
	);
}

/** Une las habilidades de un paso de entrevista con las ya conocidas. */
export function mergeProfileSkills(
	base: ProfileSkill[],
	extra: ProfileSkill[] = [],
) {
	const byId = new Map(base.map((s) => [s.skill.id, s]));
	for (const s of extra) byId.set(s.skill.id, s);
	return [...byId.values()];
}

// ---------------------------------------------------------------------------
// Ofertas
// ---------------------------------------------------------------------------

export type IngestOutcome = {
	posting: JobPosting;
	trace: AgentTrace[] | null;
	threadId?: string;
};

export async function ingestPosting(input: {
	companyId: string;
	text: string;
}): Promise<Result<IngestOutcome>> {
	const fromMock = (reason: string) =>
		runMock(async () => {
			const out = await mock.ingestPosting(input.companyId, input.text);
			return { posting: out.posting, trace: out.trace };
		}, reason);

	if (MOCK_MODE === "siempre") return fromMock(MOCK_ALWAYS);

	const form = new FormData();
	form.append("companyId", input.companyId);
	form.append("text", input.text);

	const r = await attempt(
		(signal) =>
			api.POST("/postings", {
				body: { companyId: input.companyId, text: input.text },
				bodySerializer: () => form,
				signal,
			}),
		60_000,
	);
	if (r.kind === "error")
		return { ok: false, message: r.message, problem: r.problem };
	if (r.kind === "unavailable") {
		if (MOCK_MODE === "nunca") return { ok: false, message: r.reason };
		return fromMock(r.reason);
	}

	const { threadId, resourceId } = r.data;
	const trace = await waitForTrace(threadId);
	if (trace?.status === "error") {
		return {
			ok: false,
			message: "El agente de Mercado no pudo procesar la oferta.",
		};
	}
	if (!resourceId) {
		return {
			ok: false,
			message:
				"La API aceptó la oferta pero no devolvió su identificador (resourceId), así que no podemos mostrarla.",
		};
	}
	for (let i = 0; i < (trace ? 3 : 20); i++) {
		const posting = await attempt(
			(signal) =>
				api.GET("/postings/{postingId}", {
					params: { path: { postingId: resourceId } },
					signal,
				}),
			8000,
		);
		if (posting.kind === "ok") {
			return {
				ok: true,
				data: { posting: posting.data, trace: trace?.steps ?? null, threadId },
				source: "api",
			};
		}
		if (posting.kind === "error") {
			return { ok: false, message: posting.message, problem: posting.problem };
		}
		await sleep(1500);
	}
	return {
		ok: false,
		message:
			"Mercado sigue trabajando en la oferta. Aparecerá en tu listado cuando termine.",
	};
}
