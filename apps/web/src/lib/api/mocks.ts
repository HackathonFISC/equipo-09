/**
 * Datos de ejemplo tipados con el contrato OpenAPI. Si el contrato cambia y
 * estos datos dejan de cumplirlo, `pnpm check-types` falla.
 * Se usan solo cuando la API no responde (o con NEXT_PUBLIC_API_MOCKS=siempre).
 */
import type { JobPosting, Location, Skill } from "./client";

const id = (prefix: string, n: number) =>
	`00000000-0000-4000-8000-${prefix}${String(n).padStart(12 - prefix.length, "0")}`;

export const mockLocations = [
	{
		id: id("a", 1),
		corregimiento: "Juan Díaz",
		distrito: "Panamá",
		provincia: "Panamá",
		lat: 9.0381,
		lng: -79.4446,
	},
	{
		id: id("a", 2),
		corregimiento: "Tocumen",
		distrito: "Panamá",
		provincia: "Panamá",
		lat: 9.0756,
		lng: -79.3825,
	},
	{
		id: id("a", 3),
		corregimiento: "Bella Vista",
		distrito: "Panamá",
		provincia: "Panamá",
		lat: 8.9833,
		lng: -79.5265,
	},
	{
		id: id("a", 4),
		corregimiento: "Belisario Porras",
		distrito: "San Miguelito",
		provincia: "Panamá",
		lat: 9.0674,
		lng: -79.4926,
	},
	{
		id: id("a", 5),
		corregimiento: "Vista Alegre",
		distrito: "Arraiján",
		provincia: "Panamá Oeste",
		lat: 8.9238,
		lng: -79.6904,
	},
	{
		id: id("a", 6),
		corregimiento: "Barrio Colón",
		distrito: "La Chorrera",
		provincia: "Panamá Oeste",
		lat: 8.8796,
		lng: -79.7832,
	},
	{
		id: id("a", 7),
		corregimiento: "Ancón",
		distrito: "Panamá",
		provincia: "Panamá",
		lat: 8.9637,
		lng: -79.5513,
	},
	{
		id: id("a", 8),
		corregimiento: "Calidonia",
		distrito: "Panamá",
		provincia: "Panamá",
		lat: 8.9667,
		lng: -79.5333,
	},
] satisfies Location[];

export const mockSkills = [
	{ id: id("b", 1), labelEs: "Atención al cliente", group: "Servicio" },
	{ id: id("b", 2), labelEs: "Manejo de caja", group: "Comercio" },
	{ id: id("b", 3), labelEs: "Control de inventario", group: "Logística" },
	{ id: id("b", 4), labelEs: "Excel básico", group: "Ofimática" },
	{ id: id("b", 5), labelEs: "Redacción de correos", group: "Ofimática" },
	{ id: id("b", 6), labelEs: "Inglés conversacional", group: "Idiomas" },
	{ id: id("b", 7), labelEs: "Manipulación de alimentos", group: "Servicio" },
	{ id: id("b", 8), labelEs: "Carga y despacho", group: "Logística" },
	{ id: id("b", 9), labelEs: "Ventas por teléfono", group: "Comercio" },
	{ id: id("b", 10), labelEs: "Trabajo en equipo", group: "Transversales" },
] satisfies Skill[];

const skill = (n: number) => mockSkills[n - 1] as Skill;
const location = (n: number) => mockLocations[n - 1] as Location;
const weekdays = (start: string, end: string) =>
	(["lun", "mar", "mie", "jue", "vie"] as const).map((day) => ({
		day,
		start,
		end,
	}));

const companyId = id("c", 1);

export const mockPostings = [
	{
		id: id("d", 1),
		companyId,
		title: "Cajera o cajero de supermercado",
		inputType: "texto",
		location: location(1),
		schedule: weekdays("08:00", "16:00"),
		salaryMin: 650,
		salaryMax: 700,
		vacancies: 3,
		status: "publicada",
		requirements: [
			{ skill: skill(2), weight: 3, required: true },
			{ skill: skill(1), weight: 2, required: true },
			{ skill: skill(10), weight: 1, required: false },
		],
		auditFindings: [],
	},
	{
		id: id("d", 2),
		companyId,
		title: "Auxiliar de bodega",
		inputType: "foto",
		location: location(2),
		schedule: [
			...weekdays("07:00", "15:00"),
			{ day: "sab", start: "07:00", end: "12:00" },
		],
		salaryMin: 640,
		vacancies: 2,
		status: "publicada",
		requirements: [
			{ skill: skill(3), weight: 3, required: true },
			{ skill: skill(8), weight: 2, required: true },
		],
		auditFindings: [],
	},
	{
		id: id("d", 3),
		companyId,
		title: "Agente de servicio al cliente bilingüe",
		inputType: "pdf",
		location: location(3),
		schedule: weekdays("09:00", "18:00"),
		salaryMin: 800,
		salaryMax: 900,
		vacancies: 5,
		status: "publicada",
		requirements: [
			{ skill: skill(6), weight: 3, required: true },
			{ skill: skill(1), weight: 2, required: true },
			{ skill: skill(5), weight: 1, required: false },
		],
		auditFindings: [],
	},
	{
		id: id("d", 4),
		companyId,
		title: "Recepcionista",
		inputType: "texto",
		location: location(8),
		schedule: weekdays("08:00", "17:00"),
		salaryMin: 650,
		vacancies: 1,
		status: "bloqueada",
		requirements: [
			{ skill: skill(1), weight: 3, required: true },
			{ skill: skill(4), weight: 2, required: false },
		],
		auditFindings: [
			{
				id: id("e", 1),
				kind: "discriminacion",
				passed: false,
				findings: [
					"«Buena presencia» no describe una habilidad. Sugerencia: «Trato amable con visitantes».",
					"«Entre 18 y 25 años» excluye por edad. Sugerencia: eliminar el rango.",
				],
			},
		],
	},
	{
		id: id("d", 5),
		companyId,
		title: "Ayudante de cocina",
		inputType: "foto",
		location: location(6),
		schedule: [
			{ day: "mie", start: "11:00", end: "19:00" },
			{ day: "jue", start: "11:00", end: "19:00" },
			{ day: "vie", start: "11:00", end: "21:00" },
			{ day: "sab", start: "11:00", end: "21:00" },
			{ day: "dom", start: "11:00", end: "17:00" },
		],
		salaryMin: 620,
		vacancies: 2,
		status: "publicada",
		requirements: [
			{ skill: skill(7), weight: 3, required: true },
			{ skill: skill(10), weight: 1, required: false },
		],
		auditFindings: [],
	},
	{
		id: id("d", 6),
		companyId,
		title: "Asistente de ventas telefónicas",
		inputType: "texto",
		location: location(4),
		schedule: weekdays("13:00", "19:00"),
		salaryMin: 600,
		salaryMax: 750,
		vacancies: 4,
		status: "borrador",
		requirements: [
			{ skill: skill(9), weight: 3, required: true },
			{ skill: skill(4), weight: 1, required: false },
		],
		auditFindings: [],
	},
] satisfies JobPosting[];
