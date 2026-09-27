// Сгенерировано `npm run gen:api` из OpenAPI сервиса. Не редактировать вручную.
export interface paths {
    "/people": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Личный состав в scope */
        get: operations["list_people_people_get"];
        put?: never;
        /** Create Person */
        post: operations["create_person_people_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/people/{person_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Карточка */
        get: operations["get_person_people__person_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Person */
        patch: operations["update_person_people__person_id__patch"];
        trace?: never;
    };
    "/people/{person_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Исключить из списков */
        post: operations["archive_person_people__person_id__archive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/people/{person_id}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Восстановить в списках */
        post: operations["restore_person_people__person_id__restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/people/transfer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Перевод в подразделение */
        post: operations["transfer_people_transfer_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/people/{person_id}/exemptions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Add Exemption */
        post: operations["add_exemption_people__person_id__exemptions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/exemptions/{exemption_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Exemption */
        put: operations["update_exemption_exemptions__exemption_id__put"];
        post?: never;
        /** Delete Exemption */
        delete: operations["delete_exemption_exemptions__exemption_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/exemptions/bulk": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Освобождение группе людей */
        post: operations["bulk_exemption_exemptions_bulk_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/people/{person_id}/clearances": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Clearances */
        get: operations["list_clearances_people__person_id__clearances_get"];
        put?: never;
        /**
         * Выдать допуск
         * @description Если человек не проходит требования роли — 422 `requirements_not_met` с перечнем нарушений в `details.violations`. Повтор с `confirm_override` и комментарием выдаёт допуск вопреки требованиям.
         */
        post: operations["grant_clearance_people__person_id__clearances_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/people/{person_id}/clearance-options": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Роли, к которым можно выдать допуск, и соответствие требованиям */
        get: operations["clearance_options_people__person_id__clearance_options_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/clearances/{clearance_id}": {
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
        /** Update Clearance */
        patch: operations["update_clearance_clearances__clearance_id__patch"];
        trace?: never;
    };
    "/clearances/{clearance_id}/revoke": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revoke Clearance */
        post: operations["revoke_clearance_clearances__clearance_id__revoke_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/clearances/bulk": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Допуск группе людей */
        post: operations["bulk_clearance_clearances_bulk_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/clearance-roles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Роли, допуски к которым оператор выдаёт своим людям */
        get: operations["clearance_roles_clearance_roles_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reports/clearance-mismatches": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Действующие допуски, не проходящие текущие требования ролей */
        get: operations["clearance_mismatches_reports_clearance_mismatches_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/positions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Positions */
        get: operations["list_positions_positions_get"];
        put?: never;
        /** Create Position */
        post: operations["create_position_positions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/positions/{item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Position */
        put: operations["update_position_positions__item_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/attribute-definitions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Attribute Definitions */
        get: operations["list_attribute_definitions_attribute_definitions_get"];
        put?: never;
        /** Create Attribute Definition */
        post: operations["create_attribute_definition_attribute_definitions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/attribute-definitions/{item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Attribute Definition */
        put: operations["update_attribute_definition_attribute_definitions__item_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/exemption-reasons": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Exemption Reasons */
        get: operations["list_exemption_reasons_exemption_reasons_get"];
        put?: never;
        /** Create Exemption Reason */
        post: operations["create_exemption_reason_exemption_reasons_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/exemption-reasons/{item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Exemption Reason */
        put: operations["update_exemption_reason_exemption_reasons__item_id__put"];
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
    "/internal/people/batch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** People Batch */
        post: operations["people_batch_internal_people_batch_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/people/availability-batch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Availability Batch
         * @description Доступность по дням: строка '1'/'0' на каждого человека. Архивные — все '0'.
         */
        post: operations["availability_batch_internal_people_availability_batch_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/references": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * References
         * @description Должности и характеристики — для проверки ссылок в требованиях ролей (scheduling).
         */
        post: operations["references_internal_references_post"];
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
        /** ArchiveIn */
        ArchiveIn: {
            /** Version */
            version: number;
            /** Comment */
            comment?: string | null;
        };
        /** AttributeDefinitionIn */
        AttributeDefinitionIn: {
            /** Code */
            code: string;
            /** Name */
            name: string;
            /**
             * Value Type
             * @enum {string}
             */
            value_type: "bool" | "int" | "enum" | "date" | "string";
            /** Enum Options */
            enum_options?: string[] | null;
            /**
             * Is Required
             * @default false
             */
            is_required: boolean;
            /**
             * Sort Order
             * @default 0
             */
            sort_order: number;
            /**
             * Is Active
             * @default true
             */
            is_active: boolean;
        };
        /** AttributeDefinitionOut */
        AttributeDefinitionOut: {
            /** Code */
            code: string;
            /** Name */
            name: string;
            /**
             * Value Type
             * @enum {string}
             */
            value_type: "bool" | "int" | "enum" | "date" | "string";
            /** Enum Options */
            enum_options?: string[] | null;
            /**
             * Is Required
             * @default false
             */
            is_required: boolean;
            /**
             * Sort Order
             * @default 0
             */
            sort_order: number;
            /**
             * Is Active
             * @default true
             */
            is_active: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
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
        /** AvailabilityIn */
        AvailabilityIn: {
            /** Person Ids */
            person_ids: string[];
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
        };
        /** AvailabilityOut */
        AvailabilityOut: {
            /**
             * Date From
             * Format: date
             */
            date_from: string;
            /** Days */
            days: number;
            /** Masks */
            masks: {
                [key: string]: string;
            };
        };
        /** BulkClearanceIn */
        BulkClearanceIn: {
            /**
             * Confirm Override
             * @default false
             */
            confirm_override: boolean;
            /** Override Comment */
            override_comment?: string | null;
            /** Valid From */
            valid_from?: string | null;
            /** Valid To */
            valid_to?: string | null;
            /** Person Ids */
            person_ids: string[];
            /** Duty Role Ids */
            duty_role_ids: string[];
        };
        /** BulkClearanceResult */
        BulkClearanceResult: {
            /** Done */
            done: number;
            /** Skipped */
            skipped?: {
                [key: string]: unknown;
            }[];
            /**
             * Needs Override
             * @default 0
             */
            needs_override: number;
        };
        /** BulkExemptionIn */
        BulkExemptionIn: {
            /**
             * Reason Id
             * Format: uuid
             */
            reason_id: string;
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
            /** Comment */
            comment?: string | null;
            /** Person Ids */
            person_ids: string[];
        };
        /** BulkResult */
        BulkResult: {
            /** Done */
            done: number;
            /** Skipped */
            skipped?: {
                [key: string]: unknown;
            }[];
        };
        /** ClearanceIn */
        ClearanceIn: {
            /**
             * Confirm Override
             * @default false
             */
            confirm_override: boolean;
            /** Override Comment */
            override_comment?: string | null;
            /** Valid From */
            valid_from?: string | null;
            /** Valid To */
            valid_to?: string | null;
            /**
             * Duty Role Id
             * Format: uuid
             */
            duty_role_id: string;
        };
        /**
         * ClearanceOption
         * @description Роль, к которой человеку можно выдать допуск, и его соответствие требованиям.
         */
        ClearanceOption: {
            /**
             * Duty Role Id
             * Format: uuid
             */
            duty_role_id: string;
            /** Role Name */
            role_name: string;
            /** Duty Type Id */
            duty_type_id: string | null;
            /** Duty Type Name */
            duty_type_name: string;
            /** Owner Unit Id */
            owner_unit_id: string | null;
            /** Owner Unit Name */
            owner_unit_name: string | null;
            /** Sort Order */
            sort_order: number;
            /** Has Requirements */
            has_requirements: boolean;
            /** Violations */
            violations: components["schemas"]["ViolationOut"][];
            /** Granted */
            granted: boolean;
        };
        /** ClearanceOut */
        ClearanceOut: {
            /**
             * Duty Role Id
             * Format: uuid
             */
            duty_role_id: string;
            /** Role Name */
            role_name: string;
            /** Duty Type Id */
            duty_type_id: string | null;
            /** Duty Type Name */
            duty_type_name: string;
            /** Owner Unit Id */
            owner_unit_id: string | null;
            /** Owner Unit Name */
            owner_unit_name: string | null;
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
            /** Valid From */
            valid_from: string | null;
            /** Valid To */
            valid_to: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "active" | "future" | "expired" | "revoked" | "role_inactive";
            /** Overrides Requirements */
            overrides_requirements: boolean;
            /** Override Comment */
            override_comment: string | null;
            /** Granted By Name */
            granted_by_name: string;
            /**
             * Granted At
             * Format: date-time
             */
            granted_at: string;
            /** Revoked At */
            revoked_at: string | null;
            /** Violations */
            violations: components["schemas"]["ViolationOut"][];
            /** Version */
            version: number;
        };
        /** ClearanceRoleOut */
        ClearanceRoleOut: {
            /**
             * Duty Role Id
             * Format: uuid
             */
            duty_role_id: string;
            /** Role Name */
            role_name: string;
            /** Duty Type Id */
            duty_type_id: string | null;
            /** Duty Type Name */
            duty_type_name: string;
            /** Owner Unit Id */
            owner_unit_id: string | null;
            /** Owner Unit Name */
            owner_unit_name: string | null;
            /** Sort Order */
            sort_order: number;
            /** Has Requirements */
            has_requirements: boolean;
        };
        /** ClearanceUpdate */
        ClearanceUpdate: {
            /** Valid From */
            valid_from?: string | null;
            /** Valid To */
            valid_to?: string | null;
            /** Version */
            version: number;
        };
        /** ExemptionIn */
        ExemptionIn: {
            /**
             * Reason Id
             * Format: uuid
             */
            reason_id: string;
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
            /** Comment */
            comment?: string | null;
        };
        /** ExemptionOut */
        ExemptionOut: {
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
            /**
             * Reason Id
             * Format: uuid
             */
            reason_id: string;
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
            /** Comment */
            comment: string | null;
            /** Version */
            version: number;
        };
        /** ExemptionReasonIn */
        ExemptionReasonIn: {
            /** Code */
            code: string;
            /** Name */
            name: string;
            /**
             * Is Active
             * @default true
             */
            is_active: boolean;
        };
        /** ExemptionReasonOut */
        ExemptionReasonOut: {
            /** Code */
            code: string;
            /** Name */
            name: string;
            /**
             * Is Active
             * @default true
             */
            is_active: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
        };
        /** ExemptionUpdate */
        ExemptionUpdate: {
            /**
             * Reason Id
             * Format: uuid
             */
            reason_id: string;
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
            /** Comment */
            comment?: string | null;
            /** Version */
            version: number;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** MismatchItem */
        MismatchItem: {
            /**
             * Duty Role Id
             * Format: uuid
             */
            duty_role_id: string;
            /** Role Name */
            role_name: string;
            /** Duty Type Id */
            duty_type_id: string | null;
            /** Duty Type Name */
            duty_type_name: string;
            /** Owner Unit Id */
            owner_unit_id: string | null;
            /** Owner Unit Name */
            owner_unit_name: string | null;
            /**
             * Clearance Id
             * Format: uuid
             */
            clearance_id: string;
            /**
             * Person Id
             * Format: uuid
             */
            person_id: string;
            /** Person Name */
            person_name: string;
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
            /** Unit Name */
            unit_name: string | null;
            /** Overrides Requirements */
            overrides_requirements: boolean;
            /** Override Comment */
            override_comment: string | null;
            /** Valid To */
            valid_to: string | null;
            /** Violations */
            violations: components["schemas"]["ViolationOut"][];
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
        /** Page[MismatchItem] */
        Page_MismatchItem_: {
            /** Items */
            items: components["schemas"]["MismatchItem"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** Page[PersonListItem] */
        Page_PersonListItem_: {
            /** Items */
            items: components["schemas"]["PersonListItem"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /**
         * PeopleBatchIn
         * @description Выборка — либо по подразделениям (действующие люди), либо по конкретным людям
         *     (включая исключённых из списков: scheduling проверяет свои назначения).
         */
        PeopleBatchIn: {
            /** Unit Ids */
            unit_ids?: string[];
            /**
             * Include Descendants
             * @default true
             */
            include_descendants: boolean;
            /** Person Ids */
            person_ids?: string[];
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
            /**
             * Include Names
             * @default false
             */
            include_names: boolean;
        };
        /** PeopleBatchPerson */
        PeopleBatchPerson: {
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
            /** Is Active */
            is_active: boolean;
            /** Rank Id */
            rank_id: string | null;
            /** Rank Order */
            rank_order: number | null;
            /** Position Id */
            position_id: string | null;
            /** Attributes */
            attributes: {
                [key: string]: unknown;
            };
            /** Exemptions */
            exemptions: [
                string,
                string
            ][];
            /** Clearances */
            clearances: [
                string,
                string | null,
                string | null
            ][];
            /** Last Name */
            last_name?: string | null;
            /** First Name */
            first_name?: string | null;
            /** Middle Name */
            middle_name?: string | null;
            /** Rank Name */
            rank_name?: string | null;
        };
        /** PersonCreate */
        PersonCreate: {
            /** Last Name */
            last_name: string;
            /** First Name */
            first_name: string;
            /** Middle Name */
            middle_name?: string | null;
            /** Rank Id */
            rank_id?: string | null;
            /** Position Id */
            position_id?: string | null;
            /** Personal No */
            personal_no?: string | null;
            /** Note */
            note?: string | null;
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
            /** Attributes */
            attributes?: {
                [key: string]: unknown;
            };
        };
        /**
         * PersonListItem
         * @description Строка списка: без характеристик и освобождений, зато с именами справочников.
         */
        PersonListItem: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Name */
            last_name: string;
            /** First Name */
            first_name: string;
            /** Middle Name */
            middle_name: string | null;
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
            /** Unit Name */
            unit_name: string | null;
            /** Rank Id */
            rank_id: string | null;
            /** Rank Name */
            rank_name: string | null;
            /** Position Id */
            position_id: string | null;
            /** Position Name */
            position_name: string | null;
            /** Personal No */
            personal_no: string | null;
            /** Is Active */
            is_active: boolean;
            /** Version */
            version: number;
        };
        /** PersonOut */
        PersonOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Name */
            last_name: string;
            /** First Name */
            first_name: string;
            /** Middle Name */
            middle_name: string | null;
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
            /** Unit Name */
            unit_name: string | null;
            /** Rank Id */
            rank_id: string | null;
            /** Rank Name */
            rank_name: string | null;
            /** Position Id */
            position_id: string | null;
            /** Position Name */
            position_name: string | null;
            /** Personal No */
            personal_no: string | null;
            /** Is Active */
            is_active: boolean;
            /** Version */
            version: number;
            /** Note */
            note: string | null;
            /** Archived At */
            archived_at: string | null;
            /** Attributes */
            attributes: {
                [key: string]: unknown;
            };
            /** Exemptions */
            exemptions: components["schemas"]["ExemptionOut"][];
            /** Can Edit */
            can_edit: boolean;
        };
        /**
         * PersonUpdate
         * @description Частичное изменение. Подразделение меняется отдельной операцией перевода.
         */
        PersonUpdate: {
            /** Version */
            version: number;
            /** Last Name */
            last_name?: string | null;
            /** First Name */
            first_name?: string | null;
            /** Middle Name */
            middle_name?: string | null;
            /** Rank Id */
            rank_id?: string | null;
            /** Position Id */
            position_id?: string | null;
            /** Personal No */
            personal_no?: string | null;
            /** Note */
            note?: string | null;
            /** Attributes */
            attributes?: {
                [key: string]: unknown;
            } | null;
        };
        /** PositionIn */
        PositionIn: {
            /** Name */
            name: string;
            /**
             * Sort Order
             * @default 0
             */
            sort_order: number;
            /**
             * Is Active
             * @default true
             */
            is_active: boolean;
        };
        /** PositionOut */
        PositionOut: {
            /** Name */
            name: string;
            /**
             * Sort Order
             * @default 0
             */
            sort_order: number;
            /**
             * Is Active
             * @default true
             */
            is_active: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
        };
        /**
         * ReferencesOut
         * @description Внутренний API для scheduling: справочники, на которые ссылаются требования ролей.
         */
        ReferencesOut: {
            /** Positions */
            positions: {
                [key: string]: unknown;
            }[];
            /** Attributes */
            attributes: {
                [key: string]: unknown;
            }[];
        };
        /** RevokeIn */
        RevokeIn: {
            /** Comment */
            comment?: string | null;
        };
        /** TransferIn */
        TransferIn: {
            /** Person Ids */
            person_ids: string[];
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
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
        /** ViolationOut */
        ViolationOut: {
            /**
             * Kind
             * @enum {string}
             */
            kind: "rank" | "position" | "attribute";
            /** Code */
            code: string | null;
            /** Message */
            message: string;
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
    list_people_people_get: {
        parameters: {
            query?: {
                unit_id?: string | null;
                subtree?: boolean;
                q?: string | null;
                rank_id?: string | null;
                position_id?: string | null;
                include_archived?: boolean;
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
                    "application/json": components["schemas"]["Page_PersonListItem_"];
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
    create_person_people_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PersonCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonOut"];
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
    get_person_people__person_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                person_id: string;
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
                    "application/json": components["schemas"]["PersonOut"];
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
    update_person_people__person_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PersonUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonOut"];
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
    archive_person_people__person_id__archive_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ArchiveIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonOut"];
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
    restore_person_people__person_id__restore_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ArchiveIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonOut"];
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
    transfer_people_transfer_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TransferIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BulkResult"];
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
    add_exemption_people__person_id__exemptions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExemptionIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExemptionOut"];
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
    update_exemption_exemptions__exemption_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                exemption_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExemptionUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExemptionOut"];
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
    delete_exemption_exemptions__exemption_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                exemption_id: string;
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
    bulk_exemption_exemptions_bulk_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BulkExemptionIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BulkResult"];
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
    list_clearances_people__person_id__clearances_get: {
        parameters: {
            query?: {
                include_revoked?: boolean;
            };
            header?: never;
            path: {
                person_id: string;
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
                    "application/json": components["schemas"]["ClearanceOut"][];
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
    grant_clearance_people__person_id__clearances_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ClearanceIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ClearanceOut"][];
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
    clearance_options_people__person_id__clearance_options_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                person_id: string;
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
                    "application/json": components["schemas"]["ClearanceOption"][];
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
    update_clearance_clearances__clearance_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                clearance_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ClearanceUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ClearanceOut"][];
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
    revoke_clearance_clearances__clearance_id__revoke_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                clearance_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RevokeIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ClearanceOut"][];
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
    bulk_clearance_clearances_bulk_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BulkClearanceIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BulkClearanceResult"];
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
    clearance_roles_clearance_roles_get: {
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
                    "application/json": components["schemas"]["ClearanceRoleOut"][];
                };
            };
        };
    };
    clearance_mismatches_reports_clearance_mismatches_get: {
        parameters: {
            query?: {
                unit_id?: string | null;
                subtree?: boolean;
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
                    "application/json": components["schemas"]["Page_MismatchItem_"];
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
    list_positions_positions_get: {
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
                    "application/json": components["schemas"]["PositionOut"][];
                };
            };
        };
    };
    create_position_positions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PositionIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PositionOut"];
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
    update_position_positions__item_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PositionIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PositionOut"];
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
    list_attribute_definitions_attribute_definitions_get: {
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
                    "application/json": components["schemas"]["AttributeDefinitionOut"][];
                };
            };
        };
    };
    create_attribute_definition_attribute_definitions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AttributeDefinitionIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributeDefinitionOut"];
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
    update_attribute_definition_attribute_definitions__item_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AttributeDefinitionIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributeDefinitionOut"];
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
    list_exemption_reasons_exemption_reasons_get: {
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
                    "application/json": components["schemas"]["ExemptionReasonOut"][];
                };
            };
        };
    };
    create_exemption_reason_exemption_reasons_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExemptionReasonIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExemptionReasonOut"];
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
    update_exemption_reason_exemption_reasons__item_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExemptionReasonIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExemptionReasonOut"];
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
    people_batch_internal_people_batch_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PeopleBatchIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PeopleBatchPerson"][];
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
    availability_batch_internal_people_availability_batch_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AvailabilityIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AvailabilityOut"];
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
    references_internal_references_post: {
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
                    "application/json": components["schemas"]["ReferencesOut"];
                };
            };
        };
    };
}
