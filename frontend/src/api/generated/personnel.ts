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
        /** PeopleBatchIn */
        PeopleBatchIn: {
            /** Unit Ids */
            unit_ids: string[];
            /**
             * Include Descendants
             * @default true
             */
            include_descendants: boolean;
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
}
