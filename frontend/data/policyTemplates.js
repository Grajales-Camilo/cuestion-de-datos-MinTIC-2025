export const POLICY_TEMPLATES = {
    mga: {
        id: 'mga',
        name: 'MGA (Proyecto de Inversión)',
        description: 'Metodología General Ajustada para proyectos públicos.',
        sections: {
            problem_id: {
                id: 'problem_id',
                title: 'Identificación del Problema',
                content: '',
                placeholder: 'Describe la necesidad o problema central que busca resolver el proyecto...'
            },
            stakeholders: {
                id: 'stakeholders',
                title: 'Análisis de Involucrados',
                content: '',
                placeholder: 'Identifica grupos afectados, beneficiarios y cooperantes...'
            },
            objective: {
                id: 'objective',
                title: 'Objetivo General',
                content: '',
                placeholder: 'Define el propósito central del proyecto (debe solucionar el problema)...'
            },
            alternatives: {
                id: 'alternatives',
                title: 'Alternativas de Solución',
                content: '',
                placeholder: 'Plantea diferentes estrategias para alcanzar el objetivo...'
            }
        }
    },
    conpes: {
        id: 'conpes',
        name: 'CONPES (Política Nacional)',
        description: 'Documento de política económica y social.',
        sections: {
            diagnosis: {
                id: 'diagnosis',
                title: 'Diagnóstico y Antecedentes',
                content: '',
                placeholder: 'Análisis de la situación actual y evolución histórica del problema...'
            },
            concept: {
                id: 'concept',
                title: 'Marco Conceptual',
                content: '',
                placeholder: 'Fundamentos teóricos y principios rectores de la política...'
            },
            action_plan: {
                id: 'action_plan',
                title: 'Plan de Acción',
                content: '',
                placeholder: 'Estrategias, líneas de acción y metas específicas...'
            },
            financing: {
                id: 'financing',
                title: 'Financiamiento',
                content: '',
                placeholder: 'Fuentes de recursos y esquema financiero...'
            }
        }
    },
    policy_brief: {
        id: 'policy_brief',
        name: 'Policy Brief (Ejecutivo)',
        description: 'Resumen ejecutivo para toma de decisiones rápida.',
        sections: {
            summary: {
                id: 'summary',
                title: 'Resumen Ejecutivo',
                content: '',
                placeholder: 'Síntesis del problema y la recomendación (máx 200 palabras)...'
            },
            context: {
                id: 'context',
                title: 'Contexto',
                content: '',
                placeholder: 'Antecedentes clave y relevancia del tema...'
            },
            recommendations: {
                id: 'recommendations',
                title: 'Recomendaciones',
                content: '',
                placeholder: 'Acciones concretas sugeridas para los tomadores de decisiones...'
            },
            implications: {
                id: 'implications',
                title: 'Implicaciones',
                content: '',
                placeholder: 'Impacto esperado, costos y consideraciones políticas...'
            }
        }
    }
};
