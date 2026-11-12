{{ config(severity='warn') }}
select * from {{ ref('fct_region_interval') }}
where demand_mw < 0 or demand_mw > 20000
