-- Use the folder's schema name as-is (staging, intermediate, marts, seeds)
-- instead of dbt's default "analytics_staging" style.
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}{{ target.schema }}{%- else -%}{{ custom_schema_name | trim }}{%- endif -%}
{%- endmacro %}
