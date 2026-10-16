/**
 * Bandeja y oportunidades simuladas para cuando la API de H3 (`/reviews`,
 * `/youth/{id}/matches`) todavía no existe. Todo se tipa con el contrato.
 *
 * AISLADO A PROPÓSITO: solo lo importa `reviews.ts`. Para quitarlo, borra este
 * archivo y las ramas `mock.*` de `reviews.ts`.
 *
 * El campo `proposal` es libre en el contrato (`additionalProperties`); las
 * formas de abajo son las que la web espera leer (ver `lib/review-proposal.ts`).
 */
import type {
	AgentTrace,
	MatchResult,
	ReviewDecision,
	ReviewTask,
} from "./client";
import { mockPostings } from "./mocks";

const id = (prefix: string, n: number) =>
	`00000000-0000-4000-8000-${prefix}${String(n).padStart(12 - prefix.length, "0")}`;

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const ago = (minutes: number) =>
	new Date(Date.now() - minutes * 60_000).toISOString();

/** Error con forma de `Problem` (409 al decidir dos veces la misma revisión). */
export class MockConflict extends Error {}

// ---------------------------------------------------------------------------
// Bandeja
// ---------------------------------------------------------------------------

const blocked = mockPostings[3];
const cashier = mockPostings[0];

function seedReviews(): ReviewTask[] {
	return [
		{
			id: id("f", 1),
			kind: "bloqueo_oferta",
			subjectId: blocked.id,
			agent: "auditor",
			status: "pendiente",
			threadId: "mock-thread-oferta",
			createdAt: ago(12),
			explanation:
				"El Auditor detuvo la oferta antes de publicarla: dos requisitos describen a la persona y no la tarea. «Buena presencia» no mide ninguna habilidad y el rango de edad excluye a personas aptas. No bloqueó nada más: salario, horario y habilidades pasaron las reglas.",
			proposal: {
				postingTitle: blocked.title,
				company: "Supermercados del Istmo",
				vacancies: blocked.vacancies,
				findings: [
					{
						rule: "Apariencia",
						quote: "Se busca recepcionista con buena presencia",
						suggestion: "Trato amable con visitantes",
					},
					{
						rule: "Edad",
						quote: "Entre 18 y 25 años",
						suggestion: "Eliminar el rango de edad",
					},
				],
				originalText:
					"Se busca recepcionista con buena presencia, entre 18 y 25 años. Lunes a viernes 8:00 a 17:00. B/. 650.",
				suggestedText:
					"Se busca recepcionista con trato amable con visitantes. Lunes a viernes 8:00 a 17:00. B/. 650.",
			},
		},
		{
			id: id("f", 2),
			kind: "lista_corta",
			subjectId: cashier.id,
			agent: "postulacion",
			status: "pendiente",
			threadId: "mock-thread-lista",
			createdAt: ago(47),
			explanation:
				"Matching eligió 3 candidatas con el solver (CP-SAT) y ninguna incumple traslado, horario ni salario. El orden sale del puntaje; Postulación redactó el CV y la carta de cada una. El Auditor repitió la corrida cambiando nombre, género y corregimiento y el orden se mantuvo (paridad 1.00).",
			proposal: {
				postingTitle: cashier.title,
				company: "Supermercados del Istmo",
				vacancies: cashier.vacancies,
				candidates: [
					{
						youthId: id("9", 1),
						displayName: "Ana R.",
						score: 0.91,
						commuteMin: 35,
						dailyCost: 1.25,
						skillCoverage: 1,
						reason:
							"Cubre manejo de caja y atención al cliente con experiencia en un minisúper; llega en 35 min.",
					},
					{
						youthId: id("9", 2),
						displayName: "Camila V.",
						score: 0.84,
						commuteMin: 48,
						dailyCost: 1.5,
						skillCoverage: 0.8,
						reason:
							"Cubre atención al cliente y caja; le falta experiencia en inventario, que es deseable.",
					},
					{
						youthId: id("9", 3),
						displayName: "Luis M.",
						score: 0.77,
						commuteMin: 62,
						dailyCost: 2.1,
						skillCoverage: 0.8,
						reason:
							"Cubre las habilidades obligatorias; es la opción con mayor tiempo de viaje.",
					},
				],
			},
		},
		{
			id: id("f", 3),
			kind: "alerta_sesgo",
			subjectId: id("7", 1),
			agent: "auditor",
			status: "pendiente",
			threadId: "mock-thread-sesgo",
			createdAt: ago(190),
			explanation:
				"La prueba contrafactual cambió solo el corregimiento de 12 candidatas y 2 salieron de la lista corta. Con 0.83 de paridad queda bajo el umbral de 0.90, así que el Auditor no libera la corrida sin revisión humana.",
			proposal: {
				variable: "corregimiento",
				parity: 0.83,
				threshold: 0.9,
				pairs: [
					{
						original: "Ana R. · Juan Díaz",
						variant: "Ana R. · Tocumen",
						scoreOriginal: 0.91,
						scoreVariant: 0.74,
						changed: true,
					},
					{
						original: "Luis M. · Bella Vista",
						variant: "Luis M. · Vista Alegre",
						scoreOriginal: 0.77,
						scoreVariant: 0.77,
						changed: false,
					},
				],
				findings: [
					"Dos candidatas pierden posición solo por vivir en Tocumen; el tiempo de viaje explica una parte, no toda la diferencia.",
				],
			},
		},
		{
			id: id("f", 4),
			kind: "lista_corta",
			subjectId: mockPostings[2].id,
			agent: "postulacion",
			status: "aprobada",
			reviewer: "Marta Quintero",
			comment: "Orden correcto.",
			threadId: "mock-thread-lista-2",
			createdAt: ago(60 * 26),
			resolvedAt: ago(60 * 25),
			explanation:
				"Dos candidatas cumplen el inglés conversacional exigido; Postulación las ordenó por cobertura de habilidades.",
			proposal: {
				postingTitle: mockPostings[2].title,
				company: "Supermercados del Istmo",
				candidates: [
					{
						youthId: id("9", 1),
						displayName: "Ana R.",
						score: 0.88,
						commuteMin: 41,
						dailyCost: 1.25,
						skillCoverage: 0.9,
						reason: "Cubre inglés conversacional y atención al cliente.",
					},
				],
			},
		},
	];
}

type ReviewState = Record<string, Partial<ReviewTask>>;
const STORE_KEY = "puente:mocks:reviews:v1";
let state: ReviewState | null = null;

function getState(): ReviewState {
	if (state) return state;
	state = {};
	try {
		const raw = globalThis.sessionStorage?.getItem(STORE_KEY);
		if (raw) state = JSON.parse(raw) as ReviewState;
	} catch {
		// sessionStorage bloqueado: seguimos solo en memoria.
	}
	return state;
}

function save() {
	try {
		globalThis.sessionStorage?.setItem(STORE_KEY, JSON.stringify(getState()));
	} catch {
		// Sin persistencia; no es crítico para la demo.
	}
}

export async function listReviews(): Promise<ReviewTask[]> {
	await wait(350);
	const overrides = getState();
	return seedReviews().map((r) => ({ ...r, ...overrides[r.id] }));
}

const STATUS_BY_DECISION = {
	aprobar: "aprobada",
	editar: "editada",
	rechazar: "rechazada",
} as const satisfies Record<ReviewDecision["decision"], ReviewTask["status"]>;

export async function decideReview(
	reviewId: string,
	body: ReviewDecision,
): Promise<void> {
	await wait(700);
	const current = (await listReviews()).find((r) => r.id === reviewId);
	if (!current) throw new MockConflict("not-found");
	if (current.status !== "pendiente") {
		throw new MockConflict("La revisión ya fue resuelta.");
	}
	getState()[reviewId] = {
		status: STATUS_BY_DECISION[body.decision],
		reviewer: body.reviewer,
		comment: body.comment,
		resolvedAt: new Date().toISOString(),
	};
	save();
}

export function trace(threadId: string): AgentTrace[] {
	const at = (step: number) => ago(60 - step * 3);
	const steps: Record<string, AgentTrace[]> = {
		"mock-thread-oferta": [
			{
				agent: "supervisor",
				step: 1,
				decision: "Enruta la oferta a Mercado",
				reason: "Entrada de texto de una empresa; sin señales de inyección.",
				durationMs: 400,
				createdAt: at(1),
			},
			{
				agent: "mercado",
				step: 2,
				decision: "Extrae 2 habilidades y las normaliza",
				reason: "Atención al cliente ← «trato con visitantes» · Excel básico",
				durationMs: 1800,
				createdAt: at(2),
			},
			{
				agent: "auditor",
				step: 3,
				decision: "Bloquea la oferta: 2 requisitos discriminatorios",
				reason:
					"Reglas activadas: apariencia (buena presencia) y edad (18–25).",
				durationMs: 900,
				createdAt: at(3),
			},
			{
				agent: "orientador",
				step: 4,
				decision: "Espera revisión humana",
				reason: "La oferta no se publica hasta que decida el orientador.",
				createdAt: at(4),
			},
		],
		"mock-thread-lista": [
			{
				agent: "matching",
				step: 1,
				decision: "Asigna 3 candidatas a la vacante",
				reason:
					"Solver CP-SAT OPTIMAL en 0.4 s; restricciones de traslado, horario y salario satisfechas.",
				durationMs: 400,
				createdAt: at(1),
			},
			{
				agent: "auditor",
				step: 2,
				decision: "Paridad contrafactual 1.00",
				reason:
					"Cambiar nombre, género o corregimiento no altera el orden de la lista.",
				durationMs: 2100,
				createdAt: at(2),
			},
			{
				agent: "postulacion",
				step: 3,
				decision: "Redacta CV y carta por candidata",
				reason: "Cada carta cita solo habilidades con evidencia en el perfil.",
				durationMs: 3200,
				createdAt: at(3),
			},
			{
				agent: "orientador",
				step: 4,
				decision: "Espera revisión humana",
				reason: "Ninguna lista corta sale a la empresa sin visto bueno.",
				createdAt: at(4),
			},
		],
		"mock-thread-sesgo": [
			{
				agent: "matching",
				step: 1,
				decision: "Ejecuta la corrida con 12 candidatas",
				reason: "Solver FEASIBLE en 5.0 s.",
				durationMs: 5000,
				createdAt: at(1),
			},
			{
				agent: "auditor",
				step: 2,
				decision: "Alerta: paridad 0.83 en corregimiento",
				reason:
					"Umbral 0.90. 2 de 12 candidatas cambian de resultado solo al variar el corregimiento.",
				durationMs: 2600,
				createdAt: at(2),
			},
			{
				agent: "orientador",
				step: 3,
				decision: "Espera revisión humana",
				reason:
					"La corrida queda retenida mientras la paridad esté bajo el umbral.",
				createdAt: at(3),
			},
		],
	};
	return steps[threadId] ?? [];
}

// ---------------------------------------------------------------------------
// Oportunidades del joven
// ---------------------------------------------------------------------------

export function matchesFor(youthId: string): MatchResult[] {
	const runId = id("7", 1);
	const base = { runId, youthId };
	return [
		{
			...base,
			postingId: mockPostings[0].id,
			score: 0.91,
			scoreBreakdown: {
				skillCoverage: 1,
				commute: 0.82,
				cost: 0.9,
				schedule: 1,
				salary: 0.8,
			},
			constraintsChecked: {
				commuteMin: 35,
				dailyCost: 1.25,
				scheduleOverlap: true,
				salaryOk: true,
			},
			explanation:
				"Ya manejaste caja y atendiste clientes en el minisúper de tu tío. Llegas en 35 minutos y gastas B/. 1.25 al día en pasaje.",
			status: "aprobado",
		},
		{
			...base,
			postingId: mockPostings[2].id,
			score: 0.62,
			scoreBreakdown: {
				skillCoverage: 0.5,
				commute: 0.7,
				cost: 0.8,
				schedule: 0.9,
				salary: 1,
				missingSkills: ["Inglés conversacional"],
			},
			constraintsChecked: {
				commuteMin: 48,
				dailyCost: 1.5,
				scheduleOverlap: true,
				salaryOk: true,
			},
			explanation:
				"Tu atención al cliente encaja y el sueldo es el más alto de tus opciones. Te falta inglés conversacional, que la empresa pide como obligatorio.",
			status: "propuesto",
		},
		{
			...base,
			postingId: mockPostings[1].id,
			score: 0.4,
			scoreBreakdown: {
				skillCoverage: 0.9,
				commute: 0,
				cost: 0.2,
				schedule: 0.8,
				salary: 0.7,
			},
			constraintsChecked: {
				commuteMin: 110,
				dailyCost: 3.6,
				scheduleOverlap: true,
				salaryOk: true,
			},
			explanation:
				"Tus habilidades de inventario encajan, pero el viaje supera tu máximo.",
			status: "rechazado",
		},
		{
			...base,
			postingId: mockPostings[4].id,
			score: 0.3,
			scoreBreakdown: {
				skillCoverage: 0.5,
				commute: 0.4,
				cost: 0.5,
				schedule: 0,
				salary: 0.6,
				missingSkills: ["Manipulación de alimentos"],
			},
			constraintsChecked: {
				commuteMin: 70,
				dailyCost: 2.4,
				scheduleOverlap: false,
				salaryOk: true,
			},
			explanation:
				"El horario de fin de semana choca con el que tú puedes trabajar.",
			status: "rechazado",
		},
	];
}
