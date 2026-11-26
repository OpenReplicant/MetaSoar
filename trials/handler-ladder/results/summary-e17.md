# E-17 summary

100 cases, chunks of 100.

## Per chunk

| chunk | n | handler | template | large | fallback | accuracy | large calls/case | large s/case | small calls/case | small s/case |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 100 | 7.0% | 17.0% | 76.0% | 1.0% | 99.0% | 1.05 | 27.3 | 1.66 | 3.5 |

## Last 100 cases

- coverage by templates + handlers: 24.0%
- accuracy of the stream: 99.0%
- paired difference: withheld, 24 baseline answers missing (run baseline.py)

## E-17 verdict lines

- withheld: the stream is incomplete (100 of 300 cases)

## Intents

| intent | cases | rungs used (handler/template/large) | highest rung reached | handler agreement | template agreement |
| --- | --- | --- | --- | --- | --- |
| compute_rate_of_change | 16 | 7/5/4 | handler | 3/3 active v2 | 3/3 active v1 |
| compute_total_cost | 13 | 0/7/6 | template | 1/5 discarded v2 | 3/3 active v2 |
| compute_difference_between_counts | 9 | 0/4/5 | template | 2/3 shadow v2 | 3/3 active v1 |
| check_function_property | 5 | 0/1/4 | template | 1/2 shadow v1 | 3/3 active v1 |
| find_minimum_count | 5 | 0/0/5 | large | 1/2 shadow v1 | 3/4 shadow v1 |
| compute_remaining_money | 5 | 0/0/5 | large | 0/2 shadow v1 | 2/4 shadow v1 |
| find_maximum_count | 4 | 0/0/4 | large | 1/1 shadow v1 | 2/3 shadow v1 |
| count_people_interviewed | 3 | 0/0/3 | large | 0/0 shadow v1 | 1/2 shadow v1 |
| compute_range_of_values | 3 | 0/0/3 | large | 0/0 shadow v1 | 1/2 shadow v1 |
| find_start_time | 3 | 0/0/3 | large | none | 2/2 shadow v1 |
| compute_mode | 3 | 0/0/3 | large | 0/0 shadow v1 | 2/2 shadow v1 |
| count_rating_exact_value | 2 | 0/0/2 | large | none | none |
| compute_max_count | 2 | 0/0/2 | large | none | none |
| compute_mean | 2 | 0/0/2 | large | none | none |
| count_students_below_threshold | 2 | 0/0/2 | large | none | none |
| compute_total_count | 2 | 0/0/2 | large | none | none |
| count_people_interviewed_no | 2 | 0/0/2 | large | none | none |
| compute_fraction_of_total | 2 | 0/0/2 | large | none | none |
| count_bottles_collected | 1 | 0/0/1 | large | none | none |
| compute_median | 1 | 0/0/1 | large | none | none |
| compute_gross_income | 1 | 0/0/1 | large | none | none |
| count_cars_in_stock | 1 | 0/0/1 | large | none | none |
| count_races_meeting_condition | 1 | 0/0/1 | large | none | none |
| compute_time_duration | 1 | 0/0/1 | large | none | none |
| compute_total_articles_read | 1 | 0/0/1 | large | none | none |
| count_players_scored_touchdowns | 1 | 0/0/1 | large | none | none |
| compute_difference_between_weights | 1 | 0/0/1 | large | none | none |
| count_farms_with_exact | 1 | 0/0/1 | large | none | none |
| compute_total_calls_made | 1 | 0/0/1 | large | none | none |
| count_students_exact_score | 1 | 0/0/1 | large | none | none |
| compute_function_property | 1 | 0/0/1 | large | none | none |
| count_people_in_state | 1 | 0/0/1 | large | none | none |
| find_maximum_rating | 1 | 0/0/1 | large | none | none |
| count_restaurants_below_threshold | 1 | 0/0/1 | large | none | none |
| compute_difference_between_costs | 1 | 0/0/1 | large | none | none |
