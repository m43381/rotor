// Сгенерировано `npm run gen:api` из OpenAPI сервиса. Не редактировать вручную.
export interface paths {
    "/operators": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Операторы в зоне ответственности */
        get: operations["list_operators_operators_get"];
        put?: never;
        /** Создать оператора с временным паролем */
        post: operations["create_operator_operators_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/operators/roles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Роли, которые можно выдать в подразделении */
        get: operations["allowed_roles_operators_roles_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/operators/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Operator */
        patch: operations["update_operator_operators__user_id__patch"];
        trace?: never;
    };
    "/operators/{user_id}/block": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Заблокировать */
        post: operations["block_operators__user_id__block_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/operators/{user_id}/unblock": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Разблокировать */
        post: operations["unblock_operators__user_id__unblock_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/operators/{user_id}/reset-password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Сбросить пароль: новый временный, все сессии завершаются */
        post: operations["reset_password_operators__user_id__reset_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/operators/{user_id}/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Завершить все сессии оператора */
        post: operations["logout_operators__user_id__logout_post"];
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
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** OperatorCreate */
        OperatorCreate: {
            /** Username */
            username: string;
            /** Last Name */
            last_name: string;
            /** First Name */
            first_name: string;
            /**
             * Role
             * @enum {string}
             */
            role: "superadmin" | "unit_admin" | "operator" | "viewer";
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
        };
        /** OperatorOut */
        OperatorOut: {
            /** Id */
            id: string;
            /** Username */
            username: string;
            /** Last Name */
            last_name: string;
            /** First Name */
            first_name: string;
            /** Full Name */
            full_name: string;
            /** Role */
            role: ("superadmin" | "unit_admin" | "operator" | "viewer") | null;
            /** Role Name */
            role_name: string;
            /** Unit Id */
            unit_id: string | null;
            /** Unit Name */
            unit_name: string | null;
            /** Enabled */
            enabled: boolean;
            /** Created At */
            created_at: string | null;
            /** Self */
            self: boolean;
            /** Can Edit */
            can_edit: boolean;
        };
        /** OperatorUpdate */
        OperatorUpdate: {
            /** Last Name */
            last_name?: string | null;
            /** First Name */
            first_name?: string | null;
            /** Role */
            role?: ("superadmin" | "unit_admin" | "operator" | "viewer") | null;
            /** Unit Id */
            unit_id?: string | null;
        };
        /** OperatorWithPassword */
        OperatorWithPassword: {
            /** Id */
            id: string;
            /** Username */
            username: string;
            /** Last Name */
            last_name: string;
            /** First Name */
            first_name: string;
            /** Full Name */
            full_name: string;
            /** Role */
            role: ("superadmin" | "unit_admin" | "operator" | "viewer") | null;
            /** Role Name */
            role_name: string;
            /** Unit Id */
            unit_id: string | null;
            /** Unit Name */
            unit_name: string | null;
            /** Enabled */
            enabled: boolean;
            /** Created At */
            created_at: string | null;
            /** Self */
            self: boolean;
            /** Can Edit */
            can_edit: boolean;
            /** Temporary Password */
            temporary_password: string;
        };
        /** OperatorsPage */
        OperatorsPage: {
            /** Items */
            items: components["schemas"]["OperatorOut"][];
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
    list_operators_operators_get: {
        parameters: {
            query?: {
                /** @description Логин или ФИО */
                q?: string | null;
                /** @description Подразделение с поддеревом */
                unit_id?: string | null;
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
                    "application/json": components["schemas"]["OperatorsPage"];
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
    create_operator_operators_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OperatorCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OperatorWithPassword"];
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
    allowed_roles_operators_roles_get: {
        parameters: {
            query: {
                unit_id: string;
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
                    "application/json": ("superadmin" | "unit_admin" | "operator" | "viewer")[];
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
    update_operator_operators__user_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OperatorUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OperatorOut"];
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
    block_operators__user_id__block_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
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
                    "application/json": components["schemas"]["OperatorOut"];
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
    unblock_operators__user_id__unblock_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
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
                    "application/json": components["schemas"]["OperatorOut"];
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
    reset_password_operators__user_id__reset_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
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
                    "application/json": components["schemas"]["OperatorWithPassword"];
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
    logout_operators__user_id__logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
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
                    "application/json": components["schemas"]["OperatorOut"];
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
