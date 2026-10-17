/**
 * Agentes simulados (Mercado, Perfil, Auditor) para cuando la API no tiene
 * todavía los endpoints de H2. Todo se construye con los tipos del contrato:
 * si el contrato cambia, `pnpm check-types` falla aquí.
 *
 * AISLADO A PROPÓSITO: solo lo importa `agents.ts`. Para quitarlo, borra este
 * archivo y las ramas `mock.*` de `agents.ts`.
 *
 * Estado: memoria del navegador + sessionStorage (se pierde al cerrar la pestaña).
 */
import type {
	AgentTrace,
	AuditCheck,
	InterviewStep,
	JobPosting,
	PostingRequirement,
	Problem,
	ProfileSkill,
	Skill,
	TimeSlot,
	Youth,
	YouthCreate,
} from "./client";
import { mockLocations, mockSkills } from "./mocks";

/** Error con forma de `Problem` (RFC 7807), como el que devolvería la API. */
export class MockProblem extends Error {
	constructor(readonly problem: Problem) {
		super(problem.detail ?? problem.title);
	}
}

// ---------------------------------------------------------------------------
// Estado de sesión
// ---------------------------------------------------------------------------

type Store = {
	youth: Record<string, Youth>;
	/** Habilidades simuladas añadidas a un joven (real o de ejemplo). */
	overlay: Record<string, ProfileSkill[]>;
	interviews: Record<string, { answers: string[] }>;
};

const STORE_KEY = "puente:mocks:v1";
let store: Store | null = null;

function getStore(): Store {
	if (store) return store;
	store = { youth: {}, overlay: {}, interviews: {} };
	try {
		const raw = globalThis.sessionStorage?.getItem(STORE_KEY);
		if (raw) store = { ...store, ...(JSON.parse(raw) as Partial<Store>) };
	} catch {
		// sessionStorage bloqueado: seguimos solo en memoria.
	}
	return store;
}

function save() {
	try {
		globalThis.sessionStorage?.setItem(STORE_KEY, JSON.stringify(getStore()));
	} catch {
		// Sin persistencia; no es crítico para la demo.
	}
}

const newId = () => globalThis.crypto.randomUUID();
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------------------
// Extracción por palabras clave (sustituto del LLM)
// ---------------------------------------------------------------------------

const SKILL_PATTERNS: [labelEs: string, pattern: RegExp][] = [
	[
		"Atención al cliente",
		/\b(atend\w*|atenci[oó]n al (cliente|p[uú]blico)|clientes?|servicio al cliente)\b/i,
	],
	["Manejo de caja", /\b(caja|cajer[oa]s?|cobr\w*|vuelto|efectivo)\b/i],
	[
		"Control de inventario",
		/\b(inventario\w*|mercanc[ií]a|bodega|surtir|reponer|cont(ar|aba|é) (los )?productos)\b/i,
	],
	["Excel básico", /\b(excel|hojas? de c[aá]lculo)\b/i],
	["Redacción de correos", /\b(correos?|e-?mails?|redact\w*)\b/i],
	["Inglés conversacional", /\b(ingl[eé]s|english|biling[uü]e)\b/i],
	[
		"Manipulación de alimentos",
		/\b(cocina\w*|alimentos?|comidas?|carn[eé] de salud|fonda)\b/i,
	],
	["Carga y despacho", /\b(carg\w*|despach\w*|entregas?|delivery)\b/i],
	[
		"Ventas por teléfono",
		/\b(vend\w*|ventas?|tel[eé]fono|telef[oó]nic\w*|llamadas?)\b/i,
	],
	[
		"Trabajo en equipo",
		/\b(en equipo|compañer[oa]s|ayud(aba|é|o) a (mi|la|los))\b/i,
	],
];

const skillByLabel = (label: string) =>
	mockSkills.find((s) => s.labelEs === label) as Skill;

function sentences(text: string) {
	return (text.match(/[^.!?\n]+[.!?]?/g) ?? [])
		.map((s) => s.trim())
		.filter(Boolean);
}

function clip(text: string, max = 180) {
	return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}

/** Devuelve cada habilidad encontrada con la frase que la justifica. */
function extractSkills(text: string) {
	const parts = sentences(text);
	const found: { skill: Skill; evidence: string }[] = [];
	for (const [label, pattern] of SKILL_PATTERNS) {
		const sentence = parts.find((s) => pattern.test(s));
		if (sentence)
			found.push({ skill: skillByLabel(label), evidence: clip(sentence) });
	}
	return found;
}

const INJECTION =
	/(ignora|olvida|ignore)\s+(todas\s+)?(las\s+|tus\s+)?(instrucciones|reglas|indicaciones)|system prompt|act[uú]a como/i;

function guardInjection(text: string) {
	if (INJECTION.test(text)) {
		throw new MockProblem({
			title: "Contenido bloqueado por guardrail",
			status: 422,
			guardrail: "inyeccion",
			detail:
				"El texto incluye instrucciones dirigidas al sistema. Las ignoramos y no procesamos el documento.",
		});
	}
}

function mergeSkills(base: ProfileSkill[], extra: ProfileSkill[]) {
	const seen = new Set(base.map((s) => s.skill.id));
	return [...base, ...extra.filter((s) => !seen.has(s.skill.id))];
}

function traceStep(
	step: number,
	agent: AgentTrace["agent"],
	decision: string,
	reason: string,
	inputSummary?: string,
): AgentTrace {
	return {
		agent,
		step,
		kind: agent === "orientador" ? "pausa_hitl" : "paso",
		tool: agent === "orientador" ? "Pausa del grafo (interrupt)" : undefined,
		decision,
		reason,
		inputSummary,
		durationMs: 300 + ((step * 977) % 1400),
		createdAt: new Date(Date.now() + step * 1000).toISOString(),
	};
}

// ---------------------------------------------------------------------------
// Jóvenes
// ---------------------------------------------------------------------------

export function isMockYouth(youthId: string) {
	return youthId in getStore().youth;
}

export function hasMockInterview(youthId: string) {
	return youthId in getStore().interviews;
}

export async function createYouth(body: YouthCreate): Promise<Youth> {
	await wait(400);
	const youth: Youth = { ...body, id: newId(), skills: [], isSynthetic: true };
	getStore().youth[youth.id] = youth;
	save();
	return youth;
}

/** Joven de ejemplo con sus habilidades simuladas, o null si no existe. */
export function getYouth(youthId: string): Youth | null {
	const youth = getStore().youth[youthId];
	if (!youth) return null;
	return { ...youth, skills: mergeSkills(youth.skills, overlay(youthId)) };
}

/** Habilidades simuladas para fusionar con un joven que sí vino de la API. */
export function overlay(youthId: string): ProfileSkill[] {
	return getStore().overlay[youthId] ?? [];
}

function addOverlay(youthId: string, skills: ProfileSkill[]) {
	const s = getStore();
	s.overlay[youthId] = mergeSkills(s.overlay[youthId] ?? [], skills);
	save();
}

const SAMPLE_CV =
	"Trabajé dos años en el minisúper de mi tío atendiendo clientes y cobrando en caja. Ayudaba a contar los productos de la bodega cada semana.";

export async function uploadCv(
	youthId: string,
	input: { text?: string; fileName?: string },
): Promise<{ skills: ProfileSkill[]; trace: AgentTrace[] }> {
	await wait(1200);
	const text = input.text?.trim() || SAMPLE_CV;
	guardInjection(text);
	const found = extractSkills(text).map(
		({ skill, evidence }): ProfileSkill => ({
			skill,
			level: /\b(años|siempre|encarga)/i.test(evidence) ? 2 : 1,
			source: "cv",
			evidence,
		}),
	);
	addOverlay(youthId, found);

	const what = input.text
		? `texto pegado (${text.length} caracteres)`
		: `archivo «${input.fileName ?? "cv"}»: los datos de ejemplo no leen PDF, se usa un CV de muestra`;
	const trace = [
		traceStep(
			1,
			"supervisor",
			"Enruta el CV al agente de Perfil",
			"Entrada de tipo CV sin señales de inyección.",
			what,
		),
		traceStep(
			2,
			"perfil",
			found.length > 0
				? `Extrae ${found.length} habilidades con evidencia`
				: "No encuentra habilidades verificables",
			found.length > 0
				? found.map((f) => `${f.skill.labelEs}: «${f.evidence}»`).join(" · ")
				: "Ninguna frase del CV describe una tarea concreta. La entrevista guiada puede completar el perfil.",
		),
	];
	return { skills: found, trace };
}

const INTERVIEW_QUESTIONS = [
	"¿Qué has hecho para ganar dinero, aunque sea informal o ayudando en tu familia?",
	"¿Alguna vez has atendido clientes o vendido algo? Cuéntame cómo era.",
	"¿Has manejado dinero, una caja o cuentas? ¿Qué hacías exactamente?",
	"¿Has ordenado, contado o cuidado mercancía, materiales o comida?",
	"¿Qué usas en el celular o la computadora además de redes sociales?",
	"¿Hablas algo de inglés u otro idioma? ¿Dónde lo usas?",
];

export async function answerInterview(
	youthId: string,
	answer: string | null,
): Promise<InterviewStep> {
	await wait(answer ? 900 : 400);
	const s = getStore();
	if (answer == null || !s.interviews[youthId]) {
		s.interviews[youthId] = { answers: [] };
	}
	const session = s.interviews[youthId] as { answers: string[] };

	if (answer != null) {
		guardInjection(answer);
		session.answers.push(answer);
		const found = extractSkills(answer).map(
			({ skill, evidence }): ProfileSkill => ({
				skill,
				level: /\b(años|siempre|todos los días|encarga)/i.test(evidence)
					? 2
					: 1,
				source: "entrevista",
				evidence,
			}),
		);
		addOverlay(youthId, found);
	}
	save();

	const index = session.answers.length;
	const discoveredSkills = overlay(youthId).filter(
		(sk) => sk.source === "entrevista",
	);
	if (index >= INTERVIEW_QUESTIONS.length) {
		return { done: true, index, discoveredSkills };
	}
	return {
		done: false,
		index,
		question: INTERVIEW_QUESTIONS[index],
		discoveredSkills,
	};
}

// ---------------------------------------------------------------------------
// Ofertas
// ---------------------------------------------------------------------------

const DISCRIMINATION: [pattern: RegExp, finding: string][] = [
	[
		/buena presencia/i,
		"«Buena presencia» no describe una habilidad. Sugerencia: «Trato amable con clientes».",
	],
	[
		/entre\s+\d{2}\s+y\s+\d{2}\s+años|\b\d{2}\s*(-|–|a)\s*\d{2}\s+años|menor(es)? de \d{2} años/i,
		"Pedir un rango de edad excluye a personas aptas. Sugerencia: eliminar el rango.",
	],
	[
		/\b(solo|sólo|únicamente)\s+(mujeres|hombres|señoritas|caballeros)\b|\bsexo\b/i,
		"Restringir por sexo es discriminatorio. Sugerencia: describir la tarea, no a la persona.",
	],
	[
		/\b(solter[oa]s?|sin hijos|estado civil)\b/i,
		"El estado civil o tener hijos no es un requisito laboral. Sugerencia: eliminarlo.",
	],
	[
		/\b(enviar|adjuntar|con)\s+foto\b/i,
		"Pedir foto expone a sesgos por apariencia. Sugerencia: no solicitarla en la postulación.",
	],
];

const DAYS: TimeSlot["day"][] = ["lun", "mar", "mie", "jue", "vie", "sab"];

function hhmm(h: number, m = 0) {
	return `${String(Math.min(h, 23)).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function parseSchedule(text: string): TimeSlot[] {
	const time =
		/(\d{1,2})(?::(\d{2}))?\s*(a\.?\s?m\.?|p\.?\s?m\.?)?\s*(?:a|-|–|hasta)\s*(\d{1,2})(?::(\d{2}))?\s*(a\.?\s?m\.?|p\.?\s?m\.?)?/i.exec(
			text,
		);
	if (!time) return [];
	const to24 = (h: number, mer?: string) =>
		mer?.toLowerCase().startsWith("p") && h < 12 ? h + 12 : h;
	let startH = to24(Number(time[1]), time[3]);
	let endH = to24(Number(time[4]), time[6]);
	if (!time[6] && endH <= startH) endH += 12;
	if (startH > 23 || endH > 23) return [];
	startH = Math.max(startH, 0);
	const start = hhmm(startH, Number(time[2] ?? 0));
	const end = hhmm(endH, Number(time[5] ?? 0));
	const days = /lunes a s[aá]bado/i.test(text) ? DAYS : DAYS.slice(0, 5);
	return days.map((day) => ({ day, start, end }));
}

function parseTitle(text: string) {
	const first = text.split("\n").find((l) => l.trim()) ?? "Oferta sin título";
	const cleaned = first
		.replace(
			/^\s*(se\s+busca|buscamos|se\s+necesita|necesitamos|vacante( de)?|se\s+solicita)[:\s]*/i,
			"",
		)
		.replace(/[.:]+\s*$/, "")
		.trim();
	const title = clip(cleaned || first.trim(), 80);
	return title.charAt(0).toUpperCase() + title.slice(1);
}

export async function ingestPosting(
	companyId: string,
	text: string,
): Promise<{ posting: JobPosting; trace: AgentTrace[] }> {
	await wait(1500);
	guardInjection(text);
	const parts = sentences(text);

	const requirements = extractSkills(text).map(
		({ skill, evidence }): PostingRequirement => {
			const optional =
				/\b(deseable|preferible|valorable|plus|opcional)\b/i.test(evidence);
			const strong = /\b(indispensable|obligatori\w*|imprescindible)\b/i.test(
				evidence,
			);
			return {
				skill,
				weight: optional ? 1 : strong ? 3 : 2,
				required: !optional,
			};
		},
	);
	const evidence = extractSkills(text);

	const location = mockLocations.find((l) =>
		new RegExp(`\\b${l.corregimiento}\\b`, "i").test(text),
	);
	const salary =
		/B\/\.?\s?(\d{3,4})(?:\s*(?:-|–|a)\s*(?:B\/\.?\s?)?(\d{3,4}))?/i.exec(text);
	const vacancies = /(\d{1,2})\s+vacantes?/i.exec(text);
	const schedule = parseSchedule(text);

	const findings = DISCRIMINATION.filter(([p]) => p.test(text)).map(
		([pattern, finding]) => {
			const quote = parts.find((s) => pattern.test(s));
			return quote ? `${finding} (Texto: «${clip(quote, 90)}»)` : finding;
		},
	);
	const audit: AuditCheck = {
		id: newId(),
		kind: "discriminacion",
		passed: findings.length === 0,
		findings,
	};

	const posting: JobPosting = {
		id: newId(),
		companyId,
		title: parseTitle(text),
		inputType: "texto",
		location,
		schedule,
		salaryMin: salary ? Number(salary[1]) : undefined,
		salaryMax: salary?.[2] ? Number(salary[2]) : undefined,
		vacancies: vacancies ? Math.max(1, Number(vacancies[1])) : 1,
		status: audit.passed ? "publicada" : "bloqueada",
		requirements,
		auditFindings: [audit],
	};

	const missing = [
		location ? null : "ubicación",
		salary ? null : "salario",
		schedule.length ? null : "horario",
	].filter(Boolean);

	const trace: AgentTrace[] = [
		traceStep(
			1,
			"supervisor",
			"Enruta la oferta a Mercado",
			"Entrada de texto de una empresa; sin señales de inyección.",
			`${text.length} caracteres`,
		),
		traceStep(
			2,
			"mercado",
			`Extrae ${requirements.length} habilidades y las normaliza a la taxonomía`,
			[
				...evidence.map((e) => `${e.skill.labelEs} ← «${e.evidence}»`),
				missing.length
					? `No encontró: ${missing.join(", ")}. La empresa puede completarlo.`
					: null,
			]
				.filter(Boolean)
				.join(" · ") || "El texto no describe tareas concretas.",
		),
		traceStep(
			3,
			"auditor",
			audit.passed
				? "Aprueba: sin requisitos discriminatorios"
				: `Bloquea la oferta: ${findings.length} requisito(s) discriminatorio(s)`,
			audit.passed
				? "Revisó edad, sexo, apariencia, estado civil y foto. Ninguna regla se activó."
				: "Se crea una tarea de revisión para el orientador antes de publicar.",
		),
	];
	if (!audit.passed) {
		trace.push(
			traceStep(
				4,
				"orientador",
				"Espera revisión humana",
				"La oferta queda en la bandeja del orientador con la sugerencia de redacción.",
			),
		);
	}
	return { posting, trace };
}
