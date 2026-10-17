/**
 * Lecturas de catálogo para Server Components. Llaman a la API con el cliente
 * tipado y, según NEXT_PUBLIC_API_MOCKS, caen a los datos de ejemplo.
 */
import {
	API_BASE_URL,
	api,
	type Course,
	type JobPosting,
	type Location,
	MOCK_MODE,
	type PostingStatus,
	type Skill,
} from "./client";
import { mockCourses } from "./mock-traces";
import { mockLocations, mockPostings, mockSkills } from "./mocks";

const TIMEOUT_MS = 2500;

export type DataSource = "api" | "mock";

export type Loaded<T> =
	| { ok: true; data: T; source: DataSource; reason?: string }
	| { ok: false; message: string };

type ApiCall<T> = (
	signal: AbortSignal,
) => Promise<{ data?: T; error?: unknown; response: Response }>;

async function withFallback<T>(
	call: ApiCall<T>,
	mock: () => T,
): Promise<Loaded<T>> {
	if (MOCK_MODE === "siempre") {
		return {
			ok: true,
			data: mock(),
			source: "mock",
			reason: "Modo de datos de ejemplo activado.",
		};
	}

	let failure: string;
	try {
		const { data, response } = await call(AbortSignal.timeout(TIMEOUT_MS));
		if (data !== undefined) return { ok: true, data, source: "api" };
		failure = `La API respondió ${response.status} en ${API_BASE_URL}.`;
	} catch {
		failure = `La API no responde en ${API_BASE_URL}.`;
	}

	if (MOCK_MODE === "nunca") return { ok: false, message: failure };
	return { ok: true, data: mock(), source: "mock", reason: failure };
}

export function loadPostings(query: { status?: PostingStatus } = {}) {
	return withFallback<JobPosting[]>(
		(signal) => api.GET("/postings", { params: { query }, signal }),
		() =>
			mockPostings.filter((p) => !query.status || p.status === query.status),
	);
}

export function loadLocations() {
	return withFallback<Location[]>(
		(signal) => api.GET("/locations", { signal }),
		() => mockLocations,
	);
}

export function loadSkills(q?: string) {
	return withFallback<Skill[]>(
		(signal) => api.GET("/skills", { params: { query: { q } }, signal }),
		() => {
			const needle = q?.trim().toLowerCase();
			return needle
				? mockSkills.filter((s) => s.labelEs.toLowerCase().includes(needle))
				: mockSkills;
		},
	);
}

export function loadCourses() {
	return withFallback<Course[]>(
		(signal) => api.GET("/courses", { signal }),
		() => mockCourses,
	);
}
