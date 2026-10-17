import {
	Building2,
	GraduationCap,
	type LucideIcon,
	UserCheck,
	UserRound,
} from "lucide-react";

export type RoleId = "joven" | "empresa" | "centro" | "orientador";

export type Role = {
	id: RoleId;
	href: `/${RoleId}`;
	label: string;
	/** Etiqueta para la navegación en pantallas angostas. */
	shortLabel: string;
	icon: LucideIcon;
	/** Lo que el rol consigue con Puente, en su propio tono (docs/04 §2). */
	promise: string;
	detail: string;
	context: string;
};

export const roles: Role[] = [
	{
		id: "joven",
		href: "/joven",
		label: "Joven",
		shortLabel: "Joven",
		icon: UserRound,
		promise: "Encuentra trabajo al que sí puedes llegar",
		detail:
			"Arma tu perfil aunque no tengas CV. Te mostramos cuánto tardas, cuánto gastas en pasaje y por qué encajas.",
		context: "Desde el celular",
	},
	{
		id: "empresa",
		href: "/empresa",
		label: "Empresa",
		shortLabel: "Empresa",
		icon: Building2,
		promise: "Publica una oferta y recibe candidatos revisados",
		detail:
			"Pega el texto de la oferta. Mercado la estructura y detiene los requisitos que discriminan.",
		context: "Laptop",
	},
	{
		id: "centro",
		href: "/centro",
		label: "Centro de formación",
		shortLabel: "Centro",
		icon: GraduationCap,
		promise: "Conecta tus cursos con vacantes reales",
		detail:
			"Carga cursos con sus habilidades y sesiones; la ruta de formación sugiere a quién inscribir.",
		context: "Laptop",
	},
	{
		id: "orientador",
		href: "/orientador",
		label: "Orientador",
		shortLabel: "Orientador",
		icon: UserCheck,
		promise: "Decida antes de que el sistema actúe",
		detail:
			"Bloqueos de ofertas, listas cortas y alertas de sesgo esperan su aprobación, con explicación y traza.",
		context: "Pantalla grande",
	},
];

export function getRole(id: RoleId): Role {
	const role = roles.find((r) => r.id === id);
	if (!role) throw new Error(`Rol desconocido: ${id}`);
	return role;
}
