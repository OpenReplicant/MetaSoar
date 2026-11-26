# E-17 summary

200 cases, chunks of 100.

## Per chunk

| chunk | n | handler | template | large | fallback | accuracy | large calls/case | large s/case | small calls/case | small s/case |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 100 | 7.0% | 17.0% | 76.0% | 1.0% | 100.0% | 1.05 | 27.3 | 1.66 | 3.5 |
| 2 | 100 | 16.0% | 29.0% | 55.0% | 2.0% | 99.0% | 0.81 | 23.3 | 2.09 | 4.9 |

## Last 150 cases

- coverage by templates + handlers: 39.3%
- accuracy of the stream: 99.3%
- paired difference: withheld, 59 baseline answers missing (run baseline.py)

## E-17 verdict lines

- withheld: the stream is incomplete (200 of 300 cases)

## Intents

| intent | cases | rungs used (handler/template/large) | highest rung reached | handler agreement | template agreement |
| --- | --- | --- | --- | --- | --- |
| compute_rate_of_change | 26 | 17/5/4 | handler | 3/3 active v2 | 3/3 active v1 |
| compute_total_cost | 22 | 0/16/6 | template | 1/5 discarded v2 | 3/3 active v2 |
| compute_difference_between_counts | 16 | 0/9/7 | template | 3/5 discarded v2 | 3/3 active v1 |
| compute_remaining_money | 14 | 0/8/6 | template | 4/5 discarded v2 | 3/3 active v2 |
| compute_mode | 9 | 3/2/4 | handler | 3/3 active v1 | 3/3 active v1 |
| compute_range_of_values | 8 | 2/0/6 | handler | 3/3 active v1 | 3/3 active v2 |
| compute_difference_between_costs | 8 | 0/0/8 | large | 2/2 shadow v2 | 4/5 discarded v2 |
| find_minimum_count | 7 | 0/1/6 | template | 3/4 shadow v1 | 3/3 active v2 |
| compute_mean | 7 | 1/0/6 | handler | 3/3 active v1 | 3/4 shadow v2 |
| check_function_property | 6 | 0/2/4 | template | 2/3 shadow v1 | 3/3 active v1 |
| find_maximum_count | 6 | 0/0/6 | handler | 3/3 active v1 | 2/4 shadow v2 |
| compute_median | 5 | 0/1/4 | template | 2/2 shadow v1 | 3/3 active v1 |
| find_start_time | 5 | 0/1/4 | template | none | 3/3 active v1 |
| count_people_interviewed_no | 5 | 0/1/4 | template | 2/2 shadow v1 | 3/3 active v1 |
| compute_total_count | 4 | 0/0/4 | template | 1/1 shadow v1 | 3/3 active v1 |
| compute_fraction_of_total | 4 | 0/0/4 | large | 0/1 shadow v1 | 2/3 shadow v1 |
| compute_probability | 4 | 0/0/4 | large | 1/1 shadow v1 | 0/3 shadow v1 |
| count_people_interviewed | 3 | 0/0/3 | large | 0/0 shadow v1 | 1/2 shadow v1 |
| compute_max_count | 3 | 0/0/3 | large | 0/0 shadow v1 | 0/2 shadow v1 |
| count_students_below_threshold | 3 | 0/0/3 | large | 0/0 shadow v1 | 1/2 shadow v1 |
| compute_function_property | 3 | 0/0/3 | large | 0/0 shadow v1 | 2/2 shadow v1 |
| count_rating_exact_value | 2 | 0/0/2 | large | none | none |
| compute_time_duration | 2 | 0/0/2 | large | none | none |
| compute_total_money_raised | 2 | 0/0/2 | large | none | none |
| compute_minimum_count | 2 | 0/0/2 | large | none | none |
| count_exact_value | 2 | 0/0/2 | large | none | none |
| count_bottles_collected | 1 | 0/0/1 | large | none | none |
| compute_gross_income | 1 | 0/0/1 | large | none | none |
| count_cars_in_stock | 1 | 0/0/1 | large | none | none |
| count_races_meeting_condition | 1 | 0/0/1 | large | none | none |
| compute_total_articles_read | 1 | 0/0/1 | large | none | none |
| count_players_scored_touchdowns | 1 | 0/0/1 | large | none | none |
| compute_difference_between_weights | 1 | 0/0/1 | large | none | none |
| count_farms_with_exact | 1 | 0/0/1 | large | none | none |
| compute_total_calls_made | 1 | 0/0/1 | large | none | none |
| count_students_exact_score | 1 | 0/0/1 | large | none | none |
| count_people_in_state | 1 | 0/0/1 | large | none | none |
| find_maximum_rating | 1 | 0/0/1 | large | none | none |
| count_restaurants_below_threshold | 1 | 0/0/1 | large | none | none |
| count_buildings_at_least | 1 | 0/0/1 | large | none | none |
| count_flocks_exact_value | 1 | 0/0/1 | large | none | none |
| count_racks_at_least | 1 | 0/0/1 | large | none | none |
| count_ponds_at_least | 1 | 0/0/1 | large | none | none |
| count_clubs_exact_value | 1 | 0/0/1 | large | none | none |
| count_stickers_in_collection | 1 | 0/0/1 | large | none | none |
| find_start_time_no | 1 | 0/0/1 | large | none | none |
| count_children_weighed_weight | 1 | 0/0/1 | large | none | none |
| compute_total_pearls_but | 1 | 0/0/1 | large | none | none |
