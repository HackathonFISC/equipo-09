/**
 * Traza de decisiones y ruta de formación (H4), llamadas desde el navegador
 * con el cliente tipado. Si la API no implementa el endpoint (sin respuesta,
 * 404, 405 o 501) y NEXT_PUBLIC_API_MOCKS lo permite, caen a `mock-traces.ts`.
 */
import {
	attempt,
	describeProblem,
	MOCK_ALWAYS,
	type Result,
	runMock,
	withMock,
} from "./agents";
import {
	API_BASE_URL,
	api,
	type Course,
	MOCK_MODE,
	type Problem,
	type Skill,
	type Trace,
	type TraceSummary,
	type TrainingPlan,
} from "./client";
import * as mockAgents from "./mock-agents";
import * as mock from "./mock-traces";
import { mockSkills } from "./mocks";

export type { Result };

export function loadTrace(threadId: string): Promise<Result<Trace>> {
	return withMock(
		(signal) =>
			api.GET("/traces/{threadId}", {
				params: { path: { threadId } },
				signal,
			}),
		async () => {
			const t = await mock.traceFor(threadId);
			if (!t) {
				throw new mockAgents.MockProblem({
					title: "Hilo no encontrado",
					status: 404,
					detail:
						"No hay traza para este hilo. Puede que el flujo no haya empezado o que el enlace esté incompleto.",
				});
			}
			return t;
		},
	);
}

/** Corridas recientes del grafo, de la más nueva a la más antigua. */
export function loadTraces(limit = 30): Promise<Result<TraceSummary[]>> {
	return withMock(
		(signal) => api.GET("/traces", { params: { query: { limit } }, signal }),
		() => mock.listTraces(),
	);
}

/** Hilo del grafo que produjo una corrida de matching; null si no se puede saber. */
export async function loadRunThread(
	runId: string,
	simulated: boolean,
): Promise<string | null> {
	if (simulated) return mock.MOCK_THREAD_RUN;
	const r = await attempt(
		(signal) =>
			api.GET("/match-runs/{runId}", {
				params: { path: { runId } },
				signal,
			}),
		8000,
	);
	return r.kind === "ok" ? (r.data.threadId ?? null) : null;
}

export type PlanView = {
	plan: TrainingPlan;
	courses: Course[];
	skills: Skill[];
	/** Nombre del centro por id; el contrato aún no expone un GET de centros. */
	centers: Record<string, string>;
};

export const MOCK_PLAN_THREAD = mock.MOCK_THREAD_PLAN;

/**
 * Ruta de formación junto con los cursos y habilidades necesarios para
 * explicarla (centro, horas, costo, habilidad que cierra). El contrato del
 * plan solo trae título y sesión; el resto se cruza por título de curso.
 *
 * `data: null` = el joven todavía no tiene ruta (la API responde 404). No es
 * un error ni un motivo para mostrar datos de ejemplo: la pantalla ofrece
 * calcularla.
 */
export async function loadTrainingPlan(
	youthId: string,
): Promise<Result<PlanView | null>> {
	if (MOCK_MODE === "siempre" || mockAgents.isMockYouth(youthId)) {
		return runMock(
			async () => ({
				plan: await mock.trainingPlanFor(youthId),
				courses: mock.mockCourses,
				skills: mockSkills,
				centers: mock.mockCenters,
			}),
			MOCK_MODE === "siempre" ? MOCK_ALWAYS : "Perfil de ejemplo.",
		);
	}

	let plan: TrainingPlan;
	try {
		const { data, error, response } = await api.GET(
			"/youth/{youthId}/training-plan",
			{ params: { path: { youthId } }, signal: AbortSignal.timeout(10_000) },
		);
		if (response.status === 404) {
			return { ok: true, data: null, source: "api" };
		}
		if (!response.ok || data === undefined) {
			const problem = error as Problem | undefined;
			return {
				ok: false,
				message: describeProblem(problem, response.status),
				problem,
			};
		}
		plan = data;
	} catch {
		const reason = `La API no responde en ${API_BASE_URL}.`;
		if (MOCK_MODE === "nunca") return { ok: false, message: reason };
		return runMock(
			async () => ({
				plan: await mock.trainingPlanFor(youthId),
				courses: mock.mockCourses,
				skills: mockSkills,
				centers: mock.mockCenters,
			}),
			reason,
		);
	}

	const [courses, skills] = await Promise.all([
		attempt((signal) => api.GET("/courses", { signal }), 10_000),
		attempt((signal) => api.GET("/skills", { signal }), 10_000),
	]);
	return {
		ok: true,
		source: "api",
		data: {
			plan,
			courses: courses.kind === "ok" ? courses.data : [],
			skills: skills.kind === "ok" ? skills.data : [],
			centers: {},
		},
	};
}

/** Pide el cálculo de la ruta; devuelve el hilo para seguirlo en la traza. */
export async function requestTrainingPlan(
	youthId: string,
	{ simulated }: { simulated: boolean },
): Promise<Result<{ threadId: string }>> {
	const fromMock = (reason: string) =>
		runMock(async () => ({ threadId: mock.MOCK_THREAD_PLAN }), reason);
	if (simulated || MOCK_MODE === "siempre") {
		return fromMock(simulated ? "Perfil de ejemplo." : MOCK_ALWAYS);
	}
	const r = await attempt(
		(signal) =>
			api.POST("/youth/{youthId}/training-plan", {
				params: { path: { youthId } },
				signal,
			}),
		60_000,
	);
	if (r.kind === "ok") {
		return { ok: true, data: { threadId: r.data.threadId }, source: "api" };
	}
	if (r.kind === "error") {
		return { ok: false, message: r.message, problem: r.problem };
	}
	if (MOCK_MODE === "nunca") return { ok: false, message: r.reason };
	return fromMock(r.reason);
}
