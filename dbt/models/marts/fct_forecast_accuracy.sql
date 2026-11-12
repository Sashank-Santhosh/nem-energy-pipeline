{{ config(enabled=var('forecasts_ready')) }}
-- Scores every forecast once actuals exist; days with fewer than 48 actual half-hours are skipped.
with forecasts as (
    select regionid, issue_time, target_time, model_mw, naive_mw, 'live' as period
    from {{ source('forecasts', 'daily') }}
    union all
    select regionid, issue_time, target_time, model_mw, naive_mw, 'backtest' as period
    from {{ source('forecasts', 'backtest') }}
),
complete_days as (
    select regionid, cast(period_end - interval 30 minute as date) as d
    from {{ ref('fct_demand_half_hourly') }}
    group by 1, 2
    having count(*) = 48
),
aemo as (
    select f.regionid, f.issue_time, f.target_time, a.aemo_mw
    from forecasts f
    join {{ ref('fct_aemo_forecast') }} a
      on a.regionid = f.regionid and a.target_time = f.target_time and a.issue_time <= f.issue_time
    qualify row_number() over (partition by f.regionid, f.issue_time, f.target_time, f.period
                               order by a.issue_time desc) = 1
)
select f.regionid, f.target_time, f.issue_time, f.period,
       h.demand_mw as actual_mw, f.model_mw, f.naive_mw, a.aemo_mw,
       abs(f.model_mw - h.demand_mw) as model_abs_err,
       abs(f.naive_mw - h.demand_mw) as naive_abs_err,
       abs(a.aemo_mw - h.demand_mw) as aemo_abs_err
from forecasts f
join {{ ref('fct_demand_half_hourly') }} h
  on h.regionid = f.regionid and h.period_end = f.target_time
join complete_days c
  on c.regionid = f.regionid and c.d = cast(f.target_time - interval 30 minute as date)
left join aemo a
  on a.regionid = f.regionid and a.issue_time = f.issue_time and a.target_time = f.target_time
