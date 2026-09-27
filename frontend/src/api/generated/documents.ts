// Сгенерировано `npm run gen:api` из OpenAPI сервиса. Не редактировать вручную.
export interface paths {
    "/imports/templates/{kind}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Скачать xlsx-шаблон со списками значений для оператора */
        get: operations["download_template_imports_templates__kind__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/imports/{kind}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Загрузить файл: разбор и предпросмотр, ничего не меняется */
        post: operations["upload_imports__kind__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/imports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Мои последние импорты */
        get: operations["list_imports_imports_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/imports/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Import */
        get: operations["get_import_imports__job_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/imports/{job_id}/rows": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Строки файла с результатом проверки */
        get: operations["import_rows_imports__job_id__rows_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/imports/{job_id}/report": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Отчёт проверки в xlsx: строки файла, результат, ошибки с подсветкой */
        get: operations["import_report_imports__job_id__report_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/imports/{job_id}/recheck": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Проверить строки заново на текущих данных */
        post: operations["recheck_imports__job_id__recheck_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/imports/{job_id}/apply": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Применить предпросмотр
         * @description Если данные изменились после проверки — 409 `import_stale`, а задача проверяется заново (её можно применить повторно). При ошибках в строках — 422, если не выбрано `skip_invalid`.
         */
        post: operations["apply_imports__job_id__apply_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/imports/{job_id}/discard": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Discard */
        post: operations["discard_imports__job_id__discard_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/print/schedules/{schedule_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** График нарядов на месяц: PDF или XLSX */
        get: operations["print_schedule_print_schedules__schedule_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/print/daily": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Суточный наряд подразделения и поддерева на дату: ведомость или приказ */
        get: operations["print_daily_print_daily_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/print/load-report": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Отчёт по нагрузке подразделения и поддерева за период: PDF или XLSX */
        get: operations["print_load_report_print_load_report_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/print/html/{form}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** HTML формы до перевода в PDF — для проверки шаблона */
        get: operations["print_html_print_html__form__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/document-settings/{unit_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Settings */
        get: operations["get_settings_document_settings__unit_id__get"];
        /** Put Settings */
        put: operations["put_settings_document_settings__unit_id__put"];
        post?: never;
        /** Удалить свои реквизиты — действуют реквизиты вышестоящего */
        delete: operations["delete_settings_document_settings__unit_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/templates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Печатные формы и шаблоны */
        get: operations["list_templates_templates_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/templates/{form}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Template */
        get: operations["get_template_templates__form__get"];
        /**
         * Загрузить свой HTML-шаблон PDF-формы (суперадминистратор)
         * @description Шаблон проверяется отрисовкой на демо-данных; при ошибке — 422 с номером строки. Предыдущие версии сохраняются.
         */
        put: operations["put_template_templates__form__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/templates/{form}/reset": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Вернуть встроенный шаблон */
        post: operations["reset_template_templates__form__reset_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/templates/{form}/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** PDF шаблона на демо-данных (без сохранения) */
        post: operations["preview_template_templates__form__preview_post"];
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
        /** ApplyIn */
        ApplyIn: {
            /**
             * Skip Invalid
             * @default false
             */
            skip_invalid: boolean;
        };
        /** Body_upload_imports__kind__post */
        Body_upload_imports__kind__post: {
            /** File */
            file: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** ImportColumn */
        ImportColumn: {
            /** Key */
            key: string;
            /** Title */
            title: string;
            /** Required */
            required: boolean;
        };
        /** ImportJobOut */
        ImportJobOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "people" | "clearances" | "exemptions";
            /**
             * Status
             * @enum {string}
             */
            status: "preview" | "applied" | "discarded";
            /** Filename */
            filename: string;
            /** Columns */
            columns: components["schemas"]["ImportColumn"][];
            /** Summary */
            summary: {
                [key: string]: number;
            };
            /** Notes */
            notes: string[];
            /** Total */
            total: number;
            /** Applied Rows */
            applied_rows: number | null;
            /** Created By Name */
            created_by_name: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Applied At */
            applied_at: string | null;
        };
        /** ImportRowView */
        ImportRowView: {
            /** Row */
            row: number;
            /** Values */
            values: {
                [key: string]: unknown;
            };
            /**
             * Action
             * @enum {string}
             */
            action: "create" | "update" | "unchanged" | "error";
            /** Label */
            label: string | null;
            /** Errors */
            errors: {
                [key: string]: unknown;
            }[];
            /** Warnings */
            warnings: {
                [key: string]: unknown;
            }[];
            /** Changes */
            changes: {
                [key: string]: unknown[];
            };
        };
        /** ImportRowsPage */
        ImportRowsPage: {
            /** Items */
            items: components["schemas"]["ImportRowView"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** PreviewIn */
        PreviewIn: {
            /** Body */
            body?: string | null;
        };
        /** Requisites */
        Requisites: {
            /** Approver Position */
            approver_position?: string | null;
            /** Approver Rank */
            approver_rank?: string | null;
            /** Approver Name */
            approver_name?: string | null;
            /** Compiler Position */
            compiler_position?: string | null;
            /** Compiler Rank */
            compiler_rank?: string | null;
            /** Compiler Name */
            compiler_name?: string | null;
        };
        /** SettingsIn */
        SettingsIn: {
            /** Approver Position */
            approver_position?: string | null;
            /** Approver Rank */
            approver_rank?: string | null;
            /** Approver Name */
            approver_name?: string | null;
            /** Compiler Position */
            compiler_position?: string | null;
            /** Compiler Rank */
            compiler_rank?: string | null;
            /** Compiler Name */
            compiler_name?: string | null;
            /** Version */
            version?: number | null;
        };
        /** SettingsOut */
        SettingsOut: {
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
            /** Unit Name */
            unit_name: string;
            own: components["schemas"]["Requisites"] | null;
            /** Version */
            version: number | null;
            effective: components["schemas"]["Requisites"] | null;
            /** Inherited From */
            inherited_from: string | null;
            /** Can Edit */
            can_edit: boolean;
        };
        /** TemplateBrief */
        TemplateBrief: {
            /**
             * Form
             * @enum {string}
             */
            form: "schedule_month" | "daily_roster" | "daily_order" | "load_report";
            /** Title */
            title: string;
            /** Formats */
            formats: string[];
            /** Custom */
            custom: boolean;
            /** Updated At */
            updated_at: string | null;
            /** Updated By Name */
            updated_by_name: string | null;
            /** Comment */
            comment: string | null;
        };
        /** TemplateIn */
        TemplateIn: {
            /** Body */
            body: string;
            /** Comment */
            comment?: string | null;
        };
        /** TemplateOut */
        TemplateOut: {
            /**
             * Form
             * @enum {string}
             */
            form: "schedule_month" | "daily_roster" | "daily_order" | "load_report";
            /** Title */
            title: string;
            /** Body */
            body: string;
            /** Builtin */
            builtin: string;
            /** Custom */
            custom: boolean;
            /** Variables */
            variables: string;
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
    download_template_imports_templates__kind__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                kind: "people" | "clearances" | "exemptions";
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
    upload_imports__kind__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                kind: "people" | "clearances" | "exemptions";
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_imports__kind__post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportJobOut"];
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
    list_imports_imports_get: {
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
                    "application/json": components["schemas"]["ImportJobOut"][];
                };
            };
        };
    };
    get_import_imports__job_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
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
                    "application/json": components["schemas"]["ImportJobOut"];
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
    import_rows_imports__job_id__rows_get: {
        parameters: {
            query?: {
                action?: ("create" | "update" | "unchanged" | "error") | null;
                with_warnings?: boolean;
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                job_id: string;
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
                    "application/json": components["schemas"]["ImportRowsPage"];
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
    import_report_imports__job_id__report_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
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
    recheck_imports__job_id__recheck_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
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
                    "application/json": components["schemas"]["ImportJobOut"];
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
    apply_imports__job_id__apply_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApplyIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportJobOut"];
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
    discard_imports__job_id__discard_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
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
                    "application/json": components["schemas"]["ImportJobOut"];
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
    print_schedule_print_schedules__schedule_id__get: {
        parameters: {
            query?: {
                format?: "pdf" | "xlsx";
            };
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
                    "application/octet-stream": unknown;
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
    print_daily_print_daily_get: {
        parameters: {
            query: {
                unit_id: string;
                date: string;
                form?: "daily_roster" | "daily_order";
                format?: "pdf" | "docx";
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
                    "application/octet-stream": unknown;
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
    print_load_report_print_load_report_get: {
        parameters: {
            query: {
                unit_id: string;
                date_from: string;
                date_to: string;
                drafts?: boolean;
                format?: "pdf" | "xlsx";
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
                    "application/octet-stream": unknown;
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
    print_html_print_html__form__get: {
        parameters: {
            query?: {
                schedule_id?: string | null;
                unit_id?: string | null;
                date?: string | null;
                date_from?: string | null;
                date_to?: string | null;
                drafts?: boolean;
            };
            header?: never;
            path: {
                form: "schedule_month" | "daily_roster" | "daily_order" | "load_report";
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
                    "text/html": string;
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
    get_settings_document_settings__unit_id__get: {
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
                    "application/json": components["schemas"]["SettingsOut"];
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
    put_settings_document_settings__unit_id__put: {
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
                "application/json": components["schemas"]["SettingsIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SettingsOut"];
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
    delete_settings_document_settings__unit_id__delete: {
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
                    "application/json": components["schemas"]["SettingsOut"];
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
    list_templates_templates_get: {
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
                    "application/json": components["schemas"]["TemplateBrief"][];
                };
            };
        };
    };
    get_template_templates__form__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                form: "schedule_month" | "daily_roster" | "daily_order" | "load_report";
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
                    "application/json": components["schemas"]["TemplateOut"];
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
    put_template_templates__form__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                form: "schedule_month" | "daily_roster" | "daily_order" | "load_report";
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TemplateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TemplateOut"];
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
    reset_template_templates__form__reset_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                form: "schedule_month" | "daily_roster" | "daily_order" | "load_report";
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
                    "application/json": components["schemas"]["TemplateOut"];
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
    preview_template_templates__form__preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                form: "schedule_month" | "daily_roster" | "daily_order" | "load_report";
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PreviewIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/octet-stream": unknown;
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
