// Сгенерировано `npm run gen:api` из OpenAPI сервиса. Не редактировать вручную.
export interface paths {
    "/duty-types": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Видимые типы нарядов */
        get: operations["list_duty_types_duty_types_get"];
        put?: never;
        /** Create Duty Type */
        post: operations["create_duty_type_duty_types_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/duty-types/{type_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Duty Type */
        get: operations["get_duty_type_duty_types__type_id__get"];
        /** Update Duty Type */
        put: operations["update_duty_type_duty_types__type_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/duty-types/{type_id}/roles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Add Duty Role */
        post: operations["add_duty_role_duty_types__type_id__roles_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/duty-roles/{role_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Duty Role */
        put: operations["update_duty_role_duty_roles__role_id__put"];
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
    "/internal/duty-roles/batch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Duty Roles Batch */
        post: operations["duty_roles_batch_internal_duty_roles_batch_post"];
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
        /** AttributeRequirement */
        AttributeRequirement: {
            /** Code */
            code: string;
            op: components["schemas"]["Op"];
            /** Value */
            value: unknown;
        };
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
        /** DutyRoleBatchItem */
        DutyRoleBatchItem: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Duty Type Id
             * Format: uuid
             */
            duty_type_id: string;
            /** Code */
            code: string;
            /** Name */
            name: string;
            /** Headcount */
            headcount: number;
            /** Sort Order */
            sort_order: number;
            /** Min Rank Order */
            min_rank_order: number | null;
            /** Allowed Position Ids */
            allowed_position_ids: string[] | null;
            /** Attribute Requirements */
            attribute_requirements: {
                [key: string]: unknown;
            }[];
            /** Is Active */
            is_active: boolean;
            /** Version */
            version: number;
            duty_type: components["schemas"]["DutyTypeBrief"];
        };
        /** DutyRoleIn */
        DutyRoleIn: {
            /** Name */
            name: string;
            /** Code */
            code?: string | null;
            /**
             * Headcount
             * @default 1
             */
            headcount: number;
            /**
             * Sort Order
             * @default 0
             */
            sort_order: number;
            /** Min Rank Order */
            min_rank_order?: number | null;
            /** Allowed Position Ids */
            allowed_position_ids?: string[] | null;
            /** Attribute Requirements */
            attribute_requirements?: components["schemas"]["AttributeRequirement"][];
            /**
             * Is Active
             * @default true
             */
            is_active: boolean;
        };
        /** DutyRoleOut */
        DutyRoleOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Duty Type Id
             * Format: uuid
             */
            duty_type_id: string;
            /** Code */
            code: string;
            /** Name */
            name: string;
            /** Headcount */
            headcount: number;
            /** Sort Order */
            sort_order: number;
            /** Min Rank Order */
            min_rank_order: number | null;
            /** Allowed Position Ids */
            allowed_position_ids: string[] | null;
            /** Attribute Requirements */
            attribute_requirements: components["schemas"]["AttributeRequirement"][];
            /** Is Active */
            is_active: boolean;
            /** Version */
            version: number;
        };
        /** DutyRoleUpdate */
        DutyRoleUpdate: {
            /** Name */
            name: string;
            /** Code */
            code?: string | null;
            /**
             * Headcount
             * @default 1
             */
            headcount: number;
            /**
             * Sort Order
             * @default 0
             */
            sort_order: number;
            /** Min Rank Order */
            min_rank_order?: number | null;
            /** Allowed Position Ids */
            allowed_position_ids?: string[] | null;
            /** Attribute Requirements */
            attribute_requirements?: components["schemas"]["AttributeRequirement"][];
            /**
             * Is Active
             * @default true
             */
            is_active: boolean;
            /** Version */
            version: number;
        };
        /** DutyRolesBatchIn */
        DutyRolesBatchIn: {
            /** Role Ids */
            role_ids?: string[];
            /**
             * Include Inactive
             * @default true
             */
            include_inactive: boolean;
        };
        /** DutyTypeBrief */
        DutyTypeBrief: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Short Name */
            short_name: string | null;
            /**
             * Owner Unit Id
             * Format: uuid
             */
            owner_unit_id: string;
            /** Is Active */
            is_active: boolean;
            /** Version */
            version: number;
        };
        /** DutyTypeCreate */
        DutyTypeCreate: {
            /** Name */
            name: string;
            /** Short Name */
            short_name?: string | null;
            /** Assigned Unit Id */
            assigned_unit_id?: string | null;
            /**
             * Start Time
             * Format: time
             */
            start_time: string;
            /** Duration Minutes */
            duration_minutes: number;
            /**
             * Rest Hours
             * @default 48
             */
            rest_hours: number;
            /**
             * Load Weight
             * @default 1
             */
            load_weight: number;
            /**
             * Owner Unit Id
             * Format: uuid
             */
            owner_unit_id: string;
            /** Roles */
            roles: components["schemas"]["DutyRoleIn"][];
        };
        /** DutyTypeOut */
        DutyTypeOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Short Name */
            short_name: string | null;
            /**
             * Owner Unit Id
             * Format: uuid
             */
            owner_unit_id: string;
            /** Owner Unit Name */
            owner_unit_name: string | null;
            /** Assigned Unit Id */
            assigned_unit_id: string | null;
            /** Assigned Unit Name */
            assigned_unit_name: string | null;
            /**
             * Start Time
             * Format: time
             */
            start_time: string;
            /** Duration Minutes */
            duration_minutes: number;
            /** Rest Hours */
            rest_hours: number;
            /** Load Weight */
            load_weight: number;
            /** Is Active */
            is_active: boolean;
            /** Version */
            version: number;
            /** Roles */
            roles: components["schemas"]["DutyRoleOut"][];
            /** Can Edit */
            can_edit: boolean;
        };
        /**
         * DutyTypeUpdate
         * @description Владелец наряда не меняется: наряд другого подразделения — это другой наряд.
         */
        DutyTypeUpdate: {
            /** Name */
            name: string;
            /** Short Name */
            short_name?: string | null;
            /** Assigned Unit Id */
            assigned_unit_id?: string | null;
            /**
             * Start Time
             * Format: time
             */
            start_time: string;
            /** Duration Minutes */
            duration_minutes: number;
            /**
             * Rest Hours
             * @default 48
             */
            rest_hours: number;
            /**
             * Load Weight
             * @default 1
             */
            load_weight: number;
            /** Version */
            version: number;
            /**
             * Is Active
             * @default true
             */
            is_active: boolean;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** @enum {string} */
        Op: "eq" | "in" | "gte" | "lte";
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
    list_duty_types_duty_types_get: {
        parameters: {
            query?: {
                include_inactive?: boolean;
                /** @description Наряды, касающиеся подразделения */
                unit_id?: string | null;
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
                    "application/json": components["schemas"]["DutyTypeOut"][];
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
    create_duty_type_duty_types_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DutyTypeCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DutyTypeOut"];
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
    get_duty_type_duty_types__type_id__get: {
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
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DutyTypeOut"];
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
    update_duty_type_duty_types__type_id__put: {
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
                "application/json": components["schemas"]["DutyTypeUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DutyTypeOut"];
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
    add_duty_role_duty_types__type_id__roles_post: {
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
                "application/json": components["schemas"]["DutyRoleIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DutyTypeOut"];
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
    update_duty_role_duty_roles__role_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DutyRoleUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DutyTypeOut"];
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
    duty_roles_batch_internal_duty_roles_batch_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DutyRolesBatchIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DutyRoleBatchItem"][];
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
