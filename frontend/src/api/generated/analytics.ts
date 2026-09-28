// Сгенерировано `npm run gen:api` из OpenAPI сервиса. Не редактировать вручную.
export interface paths {
    "/metrics/overview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Нагрузка и справедливость по поддереву за период: сводка для дашборда */
        get: operations["overview_metrics_overview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/metrics/people": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Нагрузка по людям */
        get: operations["people_metrics_people_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/audit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Сводный журнал аудита всех сервисов */
        get: operations["journal_audit_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/audit/facets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Значения для фильтров журнала */
        get: operations["facets_audit_facets_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/audit/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Журнал по фильтрам в xlsx (до 50 000 записей) */
        get: operations["export_audit_export_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** Facets */
        Facets: {
            /** Entity Type */
            entity_type: string[];
            /** Action */
            action: string[];
            /** Service */
            service: string[];
        };
        /** Fairness */
        Fairness: {
            /** People */
            people: number;
            /** Mean */
            mean: number;
            /** Std */
            std: number;
            /** Gini */
            gini: number;
            /** Jain */
            jain: number;
            /** Range */
            range: number;
            /** Min */
            min: number;
            /** Max */
            max: number;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** JournalEntry */
        JournalEntry: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Service */
            service: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** Actor Id */
            actor_id: string;
            /** Actor Name */
            actor_name: string;
            /** Action */
            action: string;
            /** Entity Type */
            entity_type: string;
            /**
             * Entity Id
             * Format: uuid
             */
            entity_id: string;
            /** Unit Id */
            unit_id: string | null;
            /** Unit Name */
            unit_name: string | null;
            /** Before */
            before: {
                [key: string]: unknown;
            } | null;
            /** After */
            after: {
                [key: string]: unknown;
            } | null;
            /** Comment */
            comment: string | null;
        };
        /** JournalPage */
        JournalPage: {
            /** Items */
            items: components["schemas"]["JournalEntry"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** Overview */
        Overview: {
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
            /** Unit Name */
            unit_name: string;
            /**
             * Date From
             * Format: date
             */
            date_from: string;
            /**
             * Date To
             * Format: date
             */
            date_to: string;
            /** Drafts */
            drafts: boolean;
            /** Totals */
            totals: {
                [key: string]: number;
            };
            /** Fairness */
            fairness: {
                [key: string]: components["schemas"]["Fairness"];
            };
            /** Histogram */
            histogram: {
                [key: string]: number;
            }[];
            /** Units */
            units: components["schemas"]["UnitLoad"][];
            /** Trend */
            trend: {
                [key: string]: unknown;
            }[];
            /** Top */
            top: components["schemas"]["PersonLoad"][];
            /** Bottom */
            bottom: components["schemas"]["PersonLoad"][];
        };
        /** PeoplePage */
        PeoplePage: {
            /** Items */
            items: components["schemas"]["PersonRow"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** PersonLoad */
        PersonLoad: {
            /**
             * Person Id
             * Format: uuid
             */
            person_id: string;
            /** Person Name */
            person_name: string;
            /** Duties */
            duties: number;
            /** Duty Days */
            duty_days: number;
            /** Load */
            load: number;
            /** Holidays */
            holidays: number;
        };
        /** PersonRow */
        PersonRow: {
            /**
             * Person Id
             * Format: uuid
             */
            person_id: string;
            /** Person Name */
            person_name: string;
            /** Duties */
            duties: number;
            /** Duty Days */
            duty_days: number;
            /** Load */
            load: number;
            /** Holidays */
            holidays: number;
            /**
             * Last Date
             * Format: date
             */
            last_date: string;
        };
        /** UnitLoad */
        UnitLoad: {
            /** Unit Id */
            unit_id: string | null;
            /** Unit Name */
            unit_name: string;
            /** Own */
            own: boolean;
            /** People */
            people: number;
            /** Duties */
            duties: number;
            /** Load */
            load: number;
            /** Load Per Person */
            load_per_person: number;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    overview_metrics_overview_get: {
        parameters: {
            query: {
                /** @description Подразделение; учитывается всё поддерево */
                unit_id: string;
                /** @description Первая дата заступления */
                date_from: string;
                /** @description Последняя дата заступления */
                date_to: string;
                /** @description Учитывать черновики графиков (№57) */
                drafts?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Overview"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    people_metrics_people_get: {
        parameters: {
            query: {
                /** @description Подразделение; учитывается всё поддерево */
                unit_id: string;
                /** @description Первая дата заступления */
                date_from: string;
                /** @description Последняя дата заступления */
                date_to: string;
                /** @description Учитывать черновики графиков (№57) */
                drafts?: boolean;
                limit?: number;
                offset?: number;
                /** @description Сначала наименее загруженные */
                ascending?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PeoplePage"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    journal_audit_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
                date_from?: string | null;
                date_to?: string | null;
                /** @description С поддеревом */
                unit_id?: string | null;
                /** @description ФИО или id оператора */
                actor?: string | null;
                entity_type?: string | null;
                entity_id?: string | null;
                /** @description Действие или его начало: person. */
                action?: string | null;
                service?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JournalPage"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    facets_audit_facets_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Facets"];
                };
            };
        };
    };
    export_audit_export_get: {
        parameters: {
            query?: {
                date_from?: string | null;
                date_to?: string | null;
                /** @description С поддеревом */
                unit_id?: string | null;
                /** @description ФИО или id оператора */
                actor?: string | null;
                entity_type?: string | null;
                entity_id?: string | null;
                /** @description Действие или его начало: person. */
                action?: string | null;
                service?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
