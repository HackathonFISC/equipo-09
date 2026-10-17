import { defineTranslations } from "fumadocs-core/i18n";
import { uiTranslations } from "fumadocs-ui/i18n";
import type { BaseLayoutProps } from "fumadocs-ui/layouts/shared";
import { appName, repoUrl } from "./shared";

export function baseOptions(): BaseLayoutProps {
	return {
		nav: { title: appName },
		githubUrl: repoUrl,
	};
}

// Fumadocs no trae paquete de idioma en español: traducimos las etiquetas visibles.
export const translations = defineTranslations().extend(uiTranslations()).add({
	displayName: "Español",
	"Back to Home(404 page)": "Volver al inicio",
	"Close Search(search dialog)(aria-label)": "Cerrar búsqueda",
	"Close Sidebar(aria-label)": "Cerrar menú lateral",
	"Close Sidebar(sidebar)(aria-label)": "Cerrar menú lateral",
	"Collapse Sidebar(sidebar)(aria-label)": "Contraer menú lateral",
	"Copied Anchor Link(heading anchor)(aria-label)": "Enlace copiado",
	"Copied Text(code block)(aria-label)": "Texto copiado",
	"Copy Anchor Link(heading anchor)(aria-label)": "Copiar enlace",
	"Copy Text(code block)(aria-label)": "Copiar texto",
	"Dark(theme switcher)(aria-label)": "Oscuro",
	"Edit on GitHub(edit page)": "Editar en GitHub",
	"Hide Sidebar(sidebar)": "Ocultar menú lateral",
	"Last updated on(page footer)": "Última actualización",
	"Light(theme switcher)(aria-label)": "Claro",
	"Next Page(pagination)": "Siguiente",
	"No Headings(table of contents)": "Sin encabezados",
	"No results found(search dialog)": "Sin resultados",
	"On this page(table of contents)": "En esta página",
	"Open Search(search trigger)(aria-label)": "Abrir búsqueda",
	"Open Sidebar(sidebar)(aria-label)": "Abrir menú lateral",
	"Page Not Found(404 page)": "Página no encontrada",
	"Previous Page(pagination)": "Anterior",
	"Search failed(search dialog)": "La búsqueda falló",
	"Search failed, showing results for {query}(search dialog)":
		"La búsqueda falló; resultados para {query}",
	"Search(search dialog)": "Buscar",
	"Search(search trigger)": "Buscar",
	"Show Sidebar(sidebar)": "Mostrar menú lateral",
	"System(theme switcher)(aria-label)": "Sistema",
	"Table of Contents(inline table of contents)": "Contenido",
	"The page you are looking for might have been removed, had its name changed, or is temporarily unavailable.(404 page)":
		"La página que buscas no existe o cambió de nombre.",
	"Toggle Menu(mobile menu)(aria-label)": "Abrir o cerrar menú",
	"Toggle Theme(theme switcher)(aria-label)": "Cambiar tema",
});
