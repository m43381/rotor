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
    "/schedules": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Графики месяца в scope */
        get: operations["list_schedules_schedules_get"];
        put?: never;
        /** Create Schedule */
        post: operations["create_schedule_schedules_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/schedules/{schedule_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Schedule */
        get: operations["get_schedule_schedules__schedule_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/schedules/{schedule_id}/table": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Таблица месяца: строки — роли нарядов, столбцы — дни */
        get: operations["schedule_table_schedules__schedule_id__table_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/schedules/{schedule_id}/delegate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Делегировать ячейки прямому дочернему подразделению или вернуть себе */
        post: operations["delegate_schedules__schedule_id__delegate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/schedules/{schedule_id}/accept": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Accept */
        post: operations["accept_schedules__schedule_id__accept_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/schedules/{schedule_id}/pin": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Pin */
        post: operations["pin_schedules__schedule_id__pin_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/schedules/{schedule_id}/publish": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Опубликовать (непринятые ячейки поддерева — предупреждение, не запрет) */
        post: operations["publish_schedules__schedule_id__publish_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/schedules/{schedule_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Archive */
        post: operations["archive_schedules__schedule_id__archive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/day-plans/{day_plan_id}/candidates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Назначенные и кандидаты: люди поддерева исполнителя с причинами непригодности */
        get: operations["candidates_day_plans__day_plan_id__candidates_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/day-plans/{day_plan_id}/assignments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Назначить человека
         * @description 422 `assignment_blocked` — жёсткие нарушения (допуск, освобождение, занят, не в подразделении); 422 `override_required` — нарушены отдых или лимит, повтор с `confirm_override` и комментарием. Нарушения — в `details.violations`.
         */
        post: operations["assign_day_plans__day_plan_id__assignments_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/assignments/{assignment_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Remove */
        delete: operations["remove_assignments__assignment_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/assignments/{assignment_id}/pin": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Pin */
        post: operations["pin_assignments__assignment_id__pin_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/duty-limits": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Limits */
        get: operations["list_limits_duty_limits_get"];
        put?: never;
        /** Create Limit */
        post: operations["create_limit_duty_limits_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/duty-limits/{limit_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Limit */
        put: operations["update_limit_duty_limits__limit_id__put"];
        post?: never;
        /** Delete Limit */
        delete: operations["delete_limit_duty_limits__limit_id__delete"];
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
        /** AcceptIn */
        AcceptIn: {
            /** Cell Ids */
            cell_ids?: string[] | null;
        };
        /** AssignIn */
        AssignIn: {
            /**
             * Person Id
             * Format: uuid
             */
            person_id: string;
            /**
             * Confirm Override
             * @default false
             */
            confirm_override: boolean;
            /** Override Comment */
            override_comment?: string | null;
        };
        /** AssignedOut */
        AssignedOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Person Id
             * Format: uuid
             */
            person_id: string;
            /** Person Name */
            person_name: string;
            /** Is Pinned */
            is_pinned: boolean;
            /** Rest Override */
            rest_override: boolean;
            /** Limit Override */
            limit_override: boolean;
            /** Override Comment */
            override_comment: string | null;
            /** Conflict */
            conflict: string | null;
            /** After Publish */
            after_publish: boolean;
        };
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
        /** CandidateOut */
        CandidateOut: {
            /**
             * Person Id
             * Format: uuid
             */
            person_id: string;
            /** Name */
            name: string;
            /** Rank Name */
            rank_name: string | null;
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
            /** Unit Name */
            unit_name: string | null;
            /** Month Total */
            month_total: number;
            /** Month Holiday */
            month_holiday: number;
            /** Last Duty */
            last_duty: string | null;
            /** Violations */
            violations: components["schemas"]["ViolationOut"][];
            /** Eligible */
            eligible: boolean;
        };
        /** CandidatesOut */
        CandidatesOut: {
            cell: components["schemas"]["CellInfo"];
            /** Assigned */
            assigned: components["schemas"]["AssignedOut"][];
            /** Candidates */
            candidates: components["schemas"]["CandidateOut"][];
        };
        /** CellInfo */
        CellInfo: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Schedule Id
             * Format: uuid
             */
            schedule_id: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Duty Type Name */
            duty_type_name: string;
            /** Role Name */
            role_name: string;
            /** Headcount */
            headcount: number;
            /**
             * Start At
             * Format: date-time
             */
            start_at: string;
            /**
             * End At
             * Format: date-time
             */
            end_at: string;
            /**
             * Executor Unit Id
             * Format: uuid
             */
            executor_unit_id: string;
            /** Can Assign */
            can_assign: boolean;
        };
        /** CellOut */
        CellOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * State
             * @enum {string}
             */
            state: "own" | "delegated_pending" | "delegated_accepted" | "incoming_pending" | "incoming_active" | "incoming_delegated_pending" | "incoming_delegated_accepted" | "inactive";
            /**
             * Executor Unit Id
             * Format: uuid
             */
            executor_unit_id: string;
            /** Is Pinned */
            is_pinned: boolean;
            /**
             * Filled
             * @default 0
             */
            filled: number;
            /** Assigned */
            assigned?: components["schemas"]["AssignedOut"][];
            /**
             * Has Conflict
             * @default false
             */
            has_conflict: boolean;
        };
        /** ChangedOut */
        ChangedOut: {
            /** Changed */
            changed: number;
        };
        /** DelegateIn */
        DelegateIn: {
            /** Cell Ids */
            cell_ids: string[];
            /**
             * Executor Unit Id
             * Format: uuid
             */
            executor_unit_id: string;
            /**
             * Drop Assignments
             * @default false
             */
            drop_assignments: boolean;
        };
        /** DutyLimitIn */
        DutyLimitIn: {
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
            /**
             * Applies To Subtree
             * @default true
             */
            applies_to_subtree: boolean;
            /** Rank Id */
            rank_id?: string | null;
            /** Position Id */
            position_id?: string | null;
            /** Max Duties */
            max_duties?: number | null;
            /** Max Holiday Duties */
            max_holiday_duties?: number | null;
        };
        /** DutyLimitOut */
        DutyLimitOut: {
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
            /**
             * Applies To Subtree
             * @default true
             */
            applies_to_subtree: boolean;
            /** Rank Id */
            rank_id?: string | null;
            /** Position Id */
            position_id?: string | null;
            /** Max Duties */
            max_duties?: number | null;
            /** Max Holiday Duties */
            max_holiday_duties?: number | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Unit Name */
            unit_name: string | null;
            /** Rank Name */
            rank_name: string | null;
            /** Version */
            version: number;
            /** Can Edit */
            can_edit: boolean;
        };
        /** DutyLimitUpdate */
        DutyLimitUpdate: {
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
            /**
             * Applies To Subtree
             * @default true
             */
            applies_to_subtree: boolean;
            /** Rank Id */
            rank_id?: string | null;
            /** Position Id */
            position_id?: string | null;
            /** Max Duties */
            max_duties?: number | null;
            /** Max Holiday Duties */
            max_holiday_duties?: number | null;
            /** Version */
            version: number;
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
        /** PendingWarning */
        PendingWarning: {
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
            /** Unit Name */
            unit_name: string | null;
            /** Count */
            count: number;
        };
        /** PinAssignmentIn */
        PinAssignmentIn: {
            /** Pinned */
            pinned: boolean;
        };
        /** PinIn */
        PinIn: {
            /** Cell Ids */
            cell_ids: string[];
            /** Pinned */
            pinned: boolean;
        };
        /** PublishOut */
        PublishOut: {
            schedule: components["schemas"]["ScheduleOut"];
            /** Warnings */
            warnings: components["schemas"]["PendingWarning"][];
        };
        /** ScheduleCreate */
        ScheduleCreate: {
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
            /**
             * Month
             * Format: date
             */
            month: string;
        };
        /** ScheduleOut */
        ScheduleOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
            /** Unit Name */
            unit_name: string | null;
            /**
             * Month
             * Format: date
             */
            month: string;
            /**
             * Status
             * @enum {string}
             */
            status: "draft" | "published" | "archived";
            /** Published At */
            published_at: string | null;
            /** Published By */
            published_by: string | null;
            /** Version */
            version: number;
            /** Can Edit */
            can_edit: boolean;
            /** Pending Incoming */
            pending_incoming: number;
        };
        /** TableDay */
        TableDay: {
            /**
             * Date
             * Format: date
             */
            date: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "workday" | "weekend" | "holiday" | "preholiday";
            /** Name */
            name: string | null;
        };
        /** TableOut */
        TableOut: {
            schedule: components["schemas"]["ScheduleOut"];
            /** Days */
            days: components["schemas"]["TableDay"][];
            /** Rows */
            rows: components["schemas"]["TableRow"][];
            /** Children */
            children: components["schemas"]["UnitRef"][];
            /** Units */
            units: {
                [key: string]: components["schemas"]["UnitRef"];
            };
        };
        /** TableRow */
        TableRow: {
            /**
             * Duty Type Id
             * Format: uuid
             */
            duty_type_id: string;
            /** Duty Type Name */
            duty_type_name: string;
            /** Duty Type Short Name */
            duty_type_short_name: string | null;
            /**
             * Owner Unit Id
             * Format: uuid
             */
            owner_unit_id: string;
            /** Owner Unit Name */
            owner_unit_name: string | null;
            /**
             * Start Time
             * Format: time
             */
            start_time: string;
            /** Duration Minutes */
            duration_minutes: number;
            /**
             * Duty Role Id
             * Format: uuid
             */
            duty_role_id: string;
            /** Role Name */
            role_name: string;
            /** Headcount */
            headcount: number;
            /** Is Active */
            is_active: boolean;
            /** Cells */
            cells: (components["schemas"]["CellOut"] | null)[];
        };
        /** UnitRef */
        UnitRef: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Short Name */
            short_name: string | null;
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
        /** VersionIn */
        VersionIn: {
            /** Version */
            version: number;
        };
        /** ViolationOut */
        ViolationOut: {
            /** Kind */
            kind: string;
            /** Message */
            message: string;
            /** Overridable */
            overridable: boolean;
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
    list_schedules_schedules_get: {
        parameters: {
            query: {
                /** @description Любой день месяца */
                month: string;
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
                    "application/json": components["schemas"]["ScheduleOut"][];
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
    create_schedule_schedules_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScheduleCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScheduleOut"];
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
    get_schedule_schedules__schedule_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                schedule_id: string;
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
                    "application/json": components["schemas"]["ScheduleOut"];
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
    schedule_table_schedules__schedule_id__table_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                schedule_id: string;
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
                    "application/json": components["schemas"]["TableOut"];
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
    delegate_schedules__schedule_id__delegate_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                schedule_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DelegateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChangedOut"];
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
    accept_schedules__schedule_id__accept_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                schedule_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AcceptIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChangedOut"];
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
    pin_schedules__schedule_id__pin_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                schedule_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PinIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChangedOut"];
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
    publish_schedules__schedule_id__publish_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                schedule_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VersionIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublishOut"];
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
    archive_schedules__schedule_id__archive_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                schedule_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VersionIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScheduleOut"];
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
    candidates_day_plans__day_plan_id__candidates_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                day_plan_id: string;
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
                    "application/json": components["schemas"]["CandidatesOut"];
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
    assign_day_plans__day_plan_id__assignments_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                day_plan_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssignIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CandidatesOut"];
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
    remove_assignments__assignment_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                assignment_id: string;
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
                    "application/json": components["schemas"]["CandidatesOut"];
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
    pin_assignments__assignment_id__pin_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                assignment_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PinAssignmentIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CandidatesOut"];
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
    list_limits_duty_limits_get: {
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
                    "application/json": components["schemas"]["DutyLimitOut"][];
                };
            };
        };
    };
    create_limit_duty_limits_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DutyLimitIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DutyLimitOut"];
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
    update_limit_duty_limits__limit_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                limit_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DutyLimitUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DutyLimitOut"];
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
    delete_limit_duty_limits__limit_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                limit_id: string;
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
