// Сгенерировано `npm run gen:api` из OpenAPI сервиса. Не редактировать вручную.
export interface paths {
    "/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Текущий оператор и его подразделение */
        get: operations["me_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/units": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Все подразделения в scope оператора */
        get: operations["list_units_units_get"];
        put?: never;
        /** Create Unit */
        post: operations["create_unit_units_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/units/{unit_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Unit */
        get: operations["get_unit_units__unit_id__get"];
        put?: never;
        post?: never;
        /** Расформировать */
        delete: operations["deactivate_unit_units__unit_id__delete"];
        options?: never;
        head?: never;
        /** Update Unit */
        patch: operations["update_unit_units__unit_id__patch"];
        trace?: never;
    };
    "/units/{unit_id}/move": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Перенос поддерева */
        post: operations["move_unit_units__unit_id__move_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/units/{unit_id}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Восстановить расформированное подразделение (ADR-0023) */
        post: operations["restore_unit_units__unit_id__restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/units/{unit_id}/purge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Удалить навсегда, если на подразделение ничего не ссылается (ADR-0023) */
        post: operations["purge_unit_units__unit_id__purge_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/units/{unit_id}/subtree": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Subtree */
        get: operations["subtree_units__unit_id__subtree_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/units/{unit_id}/ancestors": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Ancestors */
        get: operations["ancestors_units__unit_id__ancestors_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/unit-types": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Unit Types */
        get: operations["list_unit_types_unit_types_get"];
        put?: never;
        /** Create Unit Type */
        post: operations["create_unit_type_unit_types_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/unit-types/{type_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Unit Type */
        put: operations["update_unit_type_unit_types__type_id__put"];
        post?: never;
        /** Удалить тип подразделения, если подразделений этого типа нет (ADR-0023) */
        delete: operations["delete_unit_type_unit_types__type_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ranks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Ranks */
        get: operations["list_ranks_ranks_get"];
        put?: never;
        /** Create Rank */
        post: operations["create_rank_ranks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ranks/{rank_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Rank */
        put: operations["update_rank_ranks__rank_id__put"];
        post?: never;
        /** Удалить звание, если оно нигде не используется (ADR-0022) */
        delete: operations["delete_rank_ranks__rank_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/calendar": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Calendar */
        get: operations["list_calendar_calendar_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/calendar/{day}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Upsert Calendar Day */
        put: operations["upsert_calendar_day_calendar__day__put"];
        post?: never;
        /** Delete Calendar Day */
        delete: operations["delete_calendar_day_calendar__day__delete"];
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
        /** List Audit */
        get: operations["list_audit_audit_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/units/batch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Units Batch */
        post: operations["units_batch_internal_units_batch_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/units/descendants-batch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Descendants Batch
         * @description Все узлы поддеревьев переданных подразделений (включая сами узлы), одним запросом:
         *     `path <@ p1 OR path <@ p2 …` — каждое условие использует GiST-индекс.
         */
        post: operations["descendants_batch_internal_units_descendants_batch_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/ranks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Ranks
         * @description Все звания, включая неактивные: у людей может остаться снятое с учёта звание.
         */
        post: operations["ranks_internal_ranks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/calendar": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Calendar
         * @description Все исключения производственного календаря — для пересинхронизации проекций.
         */
        post: operations["calendar_internal_calendar_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/audit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Журнал аудита сервиса пачками по возрастанию id */
        get: operations["export_audit_internal_audit_get"];
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
        /** AuditEntryOut */
        AuditEntryOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
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
        /** CalendarDayModel */
        CalendarDayModel: {
            /**
             * Date
             * Format: date
             */
            date: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "holiday" | "workday" | "preholiday";
            /** Name */
            name?: string | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** MeOut */
        MeOut: {
            /** Subject */
            subject: string;
            /** Username */
            username: string;
            /** Full Name */
            full_name: string;
            /** Roles */
            roles: string[];
            unit: components["schemas"]["UnitOut"];
        };
        /** Page[AuditEntryOut] */
        Page_AuditEntryOut_: {
            /** Items */
            items: components["schemas"]["AuditEntryOut"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** RankIn */
        RankIn: {
            /** Name */
            name: string;
            /** Short Name */
            short_name?: string | null;
            /** Order */
            order: number;
            /**
             * Is Active
             * @default true
             */
            is_active: boolean;
        };
        /** RankOut */
        RankOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Short Name */
            short_name: string | null;
            /** Order */
            order: number;
            /** Is Active */
            is_active: boolean;
        };
        /** UnitBrief */
        UnitBrief: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Parent Id */
            parent_id: string | null;
            /**
             * Unit Type Id
             * Format: uuid
             */
            unit_type_id: string;
            /** Name */
            name: string;
            /** Short Name */
            short_name: string | null;
            /** Path */
            path: string;
            /** Is Active */
            is_active: boolean;
            /** Version */
            version: number;
        };
        /** UnitCreate */
        UnitCreate: {
            /**
             * Parent Id
             * Format: uuid
             */
            parent_id: string;
            /**
             * Unit Type Id
             * Format: uuid
             */
            unit_type_id: string;
            /** Name */
            name: string;
            /** Short Name */
            short_name?: string | null;
            /**
             * Sort Order
             * @default 0
             */
            sort_order: number;
        };
        /** UnitMove */
        UnitMove: {
            /** Version */
            version: number;
            /**
             * New Parent Id
             * Format: uuid
             */
            new_parent_id: string;
        };
        /** UnitOut */
        UnitOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Parent Id */
            parent_id: string | null;
            /**
             * Unit Type Id
             * Format: uuid
             */
            unit_type_id: string;
            /** Name */
            name: string;
            /** Short Name */
            short_name: string | null;
            /** Path */
            path: string;
            /** Depth */
            depth: number;
            /** Sort Order */
            sort_order: number;
            /** Is Active */
            is_active: boolean;
            /** Version */
            version: number;
            permissions?: components["schemas"]["UnitPermissions"] | null;
        };
        /**
         * UnitPermissions
         * @description Что оператор может делать с узлом. Считается сервером, чтобы UI не дублировал политику.
         */
        UnitPermissions: {
            /** Update */
            update: boolean;
            /** Move */
            move: boolean;
            /** Delete */
            delete: boolean;
            /** Create Child */
            create_child: boolean;
            /**
             * Restore
             * @default false
             */
            restore: boolean;
            /**
             * Purge
             * @default false
             */
            purge: boolean;
        };
        /** UnitTypeIn */
        UnitTypeIn: {
            /** Code */
            code: string;
            /** Name */
            name: string;
            /** Level */
            level: number;
            /**
             * Can Have Children
             * @default true
             */
            can_have_children: boolean;
        };
        /** UnitTypeOut */
        UnitTypeOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Code */
            code: string;
            /** Name */
            name: string;
            /** Level */
            level: number;
            /** Can Have Children */
            can_have_children: boolean;
        };
        /** UnitUpdate */
        UnitUpdate: {
            /** Version */
            version: number;
            /** Name */
            name?: string | null;
            /** Short Name */
            short_name?: string | null;
            /** Unit Type Id */
            unit_type_id?: string | null;
            /** Sort Order */
            sort_order?: number | null;
        };
        /**
         * UnitsBatchIn
         * @description Пустой список — все подразделения (для пересинхронизации проекций, ADR-0011).
         */
        UnitsBatchIn: {
            /** Unit Ids */
            unit_ids?: string[];
            /**
             * Include Inactive
             * @default true
             */
            include_inactive: boolean;
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
    me_me_get: {
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
                    "application/json": components["schemas"]["MeOut"];
                };
            };
        };
    };
    list_units_units_get: {
        parameters: {
            query?: {
                include_inactive?: boolean;
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
                    "application/json": components["schemas"]["UnitOut"][];
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
    create_unit_units_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UnitCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UnitOut"];
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
    get_unit_units__unit_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                unit_id: string;
            };
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
                    "application/json": components["schemas"]["UnitOut"];
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
    deactivate_unit_units__unit_id__delete: {
        parameters: {
            query: {
                version: number;
            };
            header?: never;
            path: {
                unit_id: string;
            };
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
                    "application/json": components["schemas"]["UnitOut"];
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
    update_unit_units__unit_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                unit_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UnitUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UnitOut"];
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
    move_unit_units__unit_id__move_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                unit_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UnitMove"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UnitOut"];
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
    restore_unit_units__unit_id__restore_post: {
        parameters: {
            query: {
                version: number;
            };
            header?: never;
            path: {
                unit_id: string;
            };
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
                    "application/json": components["schemas"]["UnitOut"];
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
    purge_unit_units__unit_id__purge_post: {
        parameters: {
            query: {
                version: number;
            };
            header?: never;
            path: {
                unit_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    subtree_units__unit_id__subtree_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                unit_id: string;
            };
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
                    "application/json": components["schemas"]["UnitOut"][];
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
    ancestors_units__unit_id__ancestors_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                unit_id: string;
            };
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
                    "application/json": components["schemas"]["UnitOut"][];
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
    list_unit_types_unit_types_get: {
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
                    "application/json": components["schemas"]["UnitTypeOut"][];
                };
            };
        };
    };
    create_unit_type_unit_types_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UnitTypeIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UnitTypeOut"];
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
    update_unit_type_unit_types__type_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                type_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UnitTypeIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UnitTypeOut"];
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
    delete_unit_type_unit_types__type_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                type_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    list_ranks_ranks_get: {
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
                    "application/json": components["schemas"]["RankOut"][];
                };
            };
        };
    };
    create_rank_ranks_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RankIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RankOut"];
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
    update_rank_ranks__rank_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rank_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RankIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RankOut"];
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
    delete_rank_ranks__rank_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rank_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    list_calendar_calendar_get: {
        parameters: {
            query: {
                date_from: string;
                date_to: string;
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
                    "application/json": components["schemas"]["CalendarDayModel"][];
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
    upsert_calendar_day_calendar__day__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                day: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CalendarDayModel"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CalendarDayModel"];
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
    delete_calendar_day_calendar__day__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                day: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    list_audit_audit_get: {
        parameters: {
            query?: {
                entity_type?: string | null;
                entity_id?: string | null;
                limit?: number;
                offset?: number;
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
                    "application/json": components["schemas"]["Page_AuditEntryOut_"];
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
    units_batch_internal_units_batch_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UnitsBatchIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UnitBrief"][];
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
    descendants_batch_internal_units_descendants_batch_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UnitsBatchIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UnitBrief"][];
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
    ranks_internal_ranks_post: {
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
                    "application/json": components["schemas"]["RankOut"][];
                };
            };
        };
    };
    calendar_internal_calendar_post: {
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
                    "application/json": components["schemas"]["CalendarDayModel"][];
                };
            };
        };
    };
    export_audit_internal_audit_get: {
        parameters: {
            query?: {
                after?: string | null;
                limit?: number;
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
                    "application/json": {
                        [key: string]: unknown;
                    }[];
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
