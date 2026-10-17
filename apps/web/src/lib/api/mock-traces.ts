/**
 * Trazas y ruta de formación simuladas para cuando `/traces/{threadId}` o
 * `/youth/{id}/training-plan` todavía no existen en la API (H4). Todo se tipa
 * con el contrato; reutiliza las trazas de revisión de `mock-reviews.ts`.
 *
 * AISLADO A PROPÓSITO: solo lo importa `traces.ts`. Para quitarlo, borra este
 * archivo y las ramas `mock.*` de `traces.ts`.
 */
import type { AgentTrace, Course, Trace, TrainingPlan } from "./client";
import { trace as reviewTrace } from "./mock-reviews";
import { mockSkills } from "./mocks";

const id = (prefix: string, n: number) =>
	`00000000-0000-4000-8000-${prefix}${String(n).padStart(12 - prefix.length, "0")}`;
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const ago = (minutes: number) =>
	new Date(Date.now() - minutes * 60_000).toISOString();

export const MOCK_THREAD_RUN = "mock-thread-corrida";
export const MOCK_THREAD_PLAN = "mock-thread-formacion";

/** Corrida completa de una joven: perfil, matching, auditor, postulación y decisión humana. */
function runTrace(): AgentTrace[] {
	const at = (step: number) => ago(90 - step * 6);
	return [
		{
			agent: "supervisor",
			step: 1,
			inputSummary: "Solicitud: buscar oportunidades para una joven registrada",
			decision: "Enruta a Perfil y luego a Matching",
			reason:
				"El perfil tiene habilidades con evidencia; no hay señales de inyección en la entrada.",
			durationMs: 300,
			createdAt: at(1),
		},
		{
			agent: "perfil",
			step: 2,
			inputSummary: "Respuestas de la entrevista (6 de 8 preguntas)",
			decision: "Anota 4 habilidades, cada una con su frase",
			reason:
				"Atención al cliente y Manejo de caja salen de «ayudaba en el minisúper de mi tío». Solo se anotó lo que ella dijo.",
			durationMs: 2400,
			createdAt: at(2),
		},
		{
			agent: "mercado",
			step: 3,
			inputSummary: "12 ofertas publicadas",
			decision: "Normaliza los requisitos de 12 ofertas",
			reason: "Cada requisito se mapea a la taxonomía ESCO-lite.",
			durationMs: 1700,
			createdAt: at(3),
		},
		{
			agent: "matching",
			step: 4,
			inputSummary: "1 joven × 12 ofertas · máx. 90 min de viaje",
			decision: "Propone 3 ofertas y descarta 9",
			reason:
				"Solver CP-SAT OPTIMAL en 0.4 s. Descartes por viaje mayor a 90 min, horario o salario bajo su mínimo.",
			durationMs: 400,
			createdAt: at(4),
		},
		{
			agent: "auditor",
			step: 5,
			inputSummary: "Prueba contrafactual: nombre, género y corregimiento",
			decision: "Paridad 1.00: el orden no cambia",
			reason:
				"Al variar nombre, género o corregimiento la lista quedó igual; no se detectó sesgo.",
			durationMs: 2100,
			createdAt: at(5),
		},
		{
			agent: "postulacion",
			step: 6,
			inputSummary: "3 ofertas aprobadas por el Auditor",
			decision: "Redacta CV y carta para cada oferta",
			reason: "Cada carta cita solo habilidades con evidencia en su perfil.",
			durationMs: 3200,
			createdAt: at(6),
		},
		{
			agent: "orientador",
			step: 7,
			inputSummary: "Lista corta de 3 ofertas con CV y cartas",
			decision: "Aprobó la lista corta (María Ríos, orientadora)",
			reason:
				"«Revisé las cartas y las tres ofertas le quedan cerca.» Con esta decisión humana el flujo se reanudó.",
			createdAt: at(7),
		},
	];
}

/** Ruta de formación: el solver elige cursos que abren más vacantes con el menor costo. */
function planTrace(): AgentTrace[] {
	const at = (step: number) => ago(40 - step * 4);
	return [
		{
			agent: "supervisor",
			step: 1,
			inputSummary: "Solicitud: calcular ruta de formación",
			decision: "Enruta al agente de Formación",
			reason: "Hay una brecha de habilidades en sus ofertas descartadas.",
			durationMs: 250,
			createdAt: at(1),
		},
		{
			agent: "formacion",
			step: 2,
			inputSummary: "4 cursos · presupuesto B/. 60 · 2 brechas",
			decision: "Elige 2 cursos en orden",
			reason:
				"El solver maximiza las vacantes que se abren dentro del presupuesto, sin chocar horarios ni pasar de 90 min de viaje.",
			durationMs: 600,
			createdAt: at(2),
		},
		{
			agent: "auditor",
			step: 3,
			inputSummary: "Cursos elegidos y cupos",
			decision: "Los cursos no dependen de nombre, género ni corregimiento",
			reason: "Se comprobó que cambiar esos datos no cambia la ruta.",
			durationMs: 1500,
			createdAt: at(3),
		},
	];
}

const STATUS: Record<string, Trace["status"]> = {
	"mock-thread-oferta": "esperando_revision",
	"mock-thread-lista": "esperando_revision",
	"mock-thread-sesgo": "esperando_revision",
	[MOCK_THREAD_RUN]: "completado",
	[MOCK_THREAD_PLAN]: "completado",
};

/** Traza de un hilo de ejemplo; null si el hilo no existe. */
export async function traceFor(threadId: string): Promise<Trace | null> {
	await wait(450);
	const steps =
		threadId === MOCK_THREAD_RUN
			? runTrace()
			: threadId === MOCK_THREAD_PLAN
				? planTrace()
				: reviewTrace(threadId);
	if (steps.length === 0) return null;
	return { threadId, status: STATUS[threadId] ?? "completado", steps };
}

// ---------------------------------------------------------------------------
// Cursos y ruta de formación
// ---------------------------------------------------------------------------

const centerA = id("e", 1);
const centerB = id("e", 2);
/** El contrato aún no expone un GET de centros: el nombre solo existe en los datos de ejemplo. */
export const mockCenters: Record<string, string> = {
	[centerA]: "Centro de Formación San Miguelito",
	[centerB]: "Escuela de Oficios Juan Díaz",
};

const sk = (n: number) => mockSkills[n - 1].id;
const slots = (
	days: ("lun" | "mar" | "mie" | "jue" | "vie" | "sab")[],
	start: string,
	end: string,
) => days.map((day) => ({ day, start, end }));

export const mockCourses: Course[] = [
	{
		id: id("a", 1),
		centerId: centerA,
		title: "Inglés conversacional para atención al público",
		hours: 40,
		cost: 25,
		skillIds: [sk(6)],
		sessions: [
			{
				id: id("5", 1),
				schedule: slots(["mar", "jue"], "17:00", "19:00"),
				startDate: "2026-11-03",
				seatsTotal: 20,
				seatsTaken: 14,
			},
		],
	},
	{
		id: id("a", 2),
		centerId: centerB,
		title: "Manipulación de alimentos (carné sanitario)",
		hours: 16,
		cost: 15,
		skillIds: [sk(7)],
		sessions: [
			{
				id: id("5", 2),
				schedule: slots(["sab"], "08:00", "12:00"),
				startDate: "2026-11-07",
				seatsTotal: 25,
				seatsTaken: 9,
			},
		],
	},
	{
		id: id("a", 3),
		centerId: centerA,
		title: "Excel básico para el trabajo",
		hours: 24,
		cost: 20,
		skillIds: [sk(4), sk(5)],
		sessions: [
			{
				id: id("5", 3),
				schedule: slots(["lun", "mie"], "18:00", "20:00"),
				startDate: "2026-11-09",
				seatsTotal: 18,
				seatsTaken: 18,
			},
			{
				id: id("5", 4),
				schedule: slots(["sab"], "13:00", "17:00"),
				startDate: "2026-11-14",
				seatsTotal: 18,
				seatsTaken: 4,
			},
		],
	},
];

export async function listCourses(): Promise<Course[]> {
	await wait(300);
	return mockCourses;
}

export async function trainingPlanFor(youthId: string): Promise<TrainingPlan> {
	await wait(500);
	const [english, food] = mockCourses;
	return {
		id: id("9", 1),
		youthId,
		items: [
			{
				courseTitle: english.title,
				session: english.sessions[0],
				commuteMin: 35,
			},
			{
				courseTitle: food.title,
				session: food.sessions[0],
				commuteMin: 50,
			},
		],
		totalCost: english.cost + food.cost,
		unlockedPostings: 3,
		explanation:
			"Te falta inglés conversacional, que piden dos ofertas a las que ya llegas en menos de una hora, y el carné de manipulación de alimentos de una tercera. Con estos dos cursos gastas B/. 40, los horarios no chocan entre sí ni con tu disponibilidad, y se abren 3 vacantes.",
	};
}
