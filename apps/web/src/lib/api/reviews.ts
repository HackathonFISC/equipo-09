/**
 * Bandeja del orientador y oportunidades del joven (H3), llamadas desde el
 * navegador con el cliente tipado. Si la API no implementa el endpoint (sin
 * respuesta, 404, 405 o 501) y NEXT_PUBLIC_API_MOCKS lo permite, caen a
 * `mock-reviews.ts`. Los errores de negocio (409, 422…) se muestran tal cual.
 */
import { attempt, MOCK_ALWAYS, type Result, runMock, withMock } from "./agents";
import {
	type AgentTrace,
	type Application,
	api,
	type JobPosting,
	type MatchResult,
	MOCK_MODE,
	type ReviewDecision,
	type ReviewTask,
} from "./client";
import * as mock from "./mock-reviews";
import { MOCK_THREAD_RUN } from "./mock-traces";
import { mockPostings } from "./mocks";

export type { Result };

export function loadReviews(): Promise<Result<ReviewTask[]>> {
	return withMock(
		(signal) => api.GET("/reviews", { signal }),
		() => mock.listReviews(),
	);
}

/**
 * Envía la decisión humana; la API reanuda el grafo detenido en `interrupt`.
 * Con datos de ejemplo la decisión solo se guarda en esta pestaña.
 */
export async function decideReview(
	reviewId: string,
	body: ReviewDecision,
	{ simulated }: { simulated: boolean },
): Promise<Result<null>> {
	const fromMock = async (reason: string): Promise<Result<null>> => {
		try {
			await mock.decideReview(reviewId, body);
		} catch (err) {
			if (err instanceof mock.MockConflict) {
				return { ok: false, message: err.message };
			}
			throw err;
		}
		return runMock(async () => null, reason);
	};

	if (simulated || MOCK_MODE === "siempre") {
		return fromMock(
			simulated
				? "Esta revisión es de ejemplo: la decisión no reanuda ningún flujo real."
				: MOCK_ALWAYS,
		);
	}
	const r = await attempt(
		(signal) =>
			api.POST("/reviews/{reviewId}/decision", {
				params: { path: { reviewId } },
				body,
				signal,
			}),
		20_000,
	);
	if (r.kind === "ok") return { ok: true, data: null, source: "api" };
	if (r.kind === "error") {
		return { ok: false, message: r.message, problem: r.problem };
	}
	if (MOCK_MODE === "nunca") return { ok: false, message: r.reason };
	return fromMock(r.reason);
}

/** Traza del hilo que originó la revisión; null si la API aún no la expone. */
export async function loadReviewTrace(
	threadId: string,
	simulated: boolean,
): Promise<AgentTrace[] | null> {
	if (simulated) return mock.trace(threadId);
	const r = await attempt(
		(signal) =>
			api.GET("/traces/{threadId}", {
				params: { path: { threadId } },
				signal,
			}),
		8000,
	);
	return r.kind === "ok" ? r.data.steps : null;
}

/**
 * Postulaciones enviadas (lista corta aprobada) de cada oferta, con sus franjas
 * de entrevista: es la acción real que deja el orientador al aprobar.
 */
export async function loadShortlists(
	postingIds: string[],
): Promise<Result<{ postingId: string; applications: Application[] }[]>> {
	const results = await Promise.all(
		postingIds.map(async (postingId) => ({
			postingId,
			r: await attempt(
				(signal) =>
					api.GET("/postings/{postingId}/shortlist", {
						params: { path: { postingId } },
						signal,
					}),
				10_000,
			),
		})),
	);
	const failed = results.find(({ r }) => r.kind !== "ok");
	if (failed && failed.r.kind === "error") {
		return { ok: false, message: failed.r.message, problem: failed.r.problem };
	}
	if (failed && failed.r.kind === "unavailable") {
		return { ok: false, message: failed.r.reason };
	}
	return {
		ok: true,
		source: "api",
		data: results.map(({ postingId, r }) => ({
			postingId,
			applications: r.kind === "ok" ? r.data : [],
		})),
	};
}

/**
 * Ejecuta Matching → Auditor → Postulación (POST /match-runs). La API corre el
 * grafo dentro de la petición y responde cuando se detiene en la revisión del
 * orientador; Postulación llama al LLM por candidato, por eso el plazo es largo.
 */
export async function runMatching(): Promise<
	Result<{ threadId: string; runId?: string }>
> {
	const fromMock = (reason: string) =>
		runMock(async () => ({ threadId: MOCK_THREAD_RUN }), reason);
	if (MOCK_MODE === "siempre") return fromMock(MOCK_ALWAYS);
	const r = await attempt(
		(signal) => api.POST("/match-runs", { body: {}, signal }),
		90_000,
	);
	if (r.kind === "ok") {
		return {
			ok: true,
			data: { threadId: r.data.threadId, runId: r.data.resourceId },
			source: "api",
		};
	}
	if (r.kind === "error") {
		return { ok: false, message: r.message, problem: r.problem };
	}
	if (MOCK_MODE === "nunca") return { ok: false, message: r.reason };
	return fromMock(r.reason);
}

// ---------------------------------------------------------------------------
// Oportunidades del joven
// ---------------------------------------------------------------------------

export type Opportunity = {
	match: MatchResult;
	/** Oferta asociada; null si no se pudo leer. */
	posting: JobPosting | null;
};

export async function loadOpportunities(
	youthId: string,
): Promise<Result<Opportunity[]>> {
	const matches = await withMock(
		(signal) =>
			api.GET("/youth/{youthId}/matches", {
				params: { path: { youthId } },
				signal,
			}),
		async () => mock.matchesFor(youthId),
	);
	if (!matches.ok) return matches;

	const postings = new Map<string, JobPosting>();
	if (matches.source === "mock") {
		for (const p of mockPostings) postings.set(p.id, p);
	} else {
		const r = await attempt(
			(signal) => api.GET("/postings", { signal }),
			10_000,
		);
		if (r.kind === "ok") for (const p of r.data) postings.set(p.id, p);
	}
	return {
		...matches,
		data: matches.data.map((match) => ({
			match,
			posting: postings.get(match.postingId) ?? null,
		})),
	};
}
