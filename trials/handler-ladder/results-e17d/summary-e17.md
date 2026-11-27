# E-17 summary

600 cases, chunks of 50.

## Per chunk

| chunk | n | handler | template | large | fallback | accuracy | large calls/case | large s/case | small calls/case | small s/case |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 100 | 7.0% | 17.0% | 76.0% | 1.0% | 100.0% | 1.05 | 27.3 | 1.66 | 3.5 |
| 2 | 100 | 16.0% | 29.0% | 55.0% | 2.0% | 99.0% | 0.81 | 23.3 | 2.09 | 4.9 |
| 3 | 100 | 32.0% | 32.0% | 36.0% | 6.0% | 97.0% | 0.50 | 17.6 | 1.80 | 5.3 |
| 7 | 50 | 26.0% | 42.0% | 32.0% | 10.0% | 100.0% | 0.46 | 13.6 | 1.64 | 3.9 |
| 8 | 50 | 44.0% | 26.0% | 30.0% | 2.0% | 88.0% | 0.40 | 11.3 | 1.46 | 2.7 |
| 9 | 50 | 44.0% | 40.0% | 16.0% | 6.0% | 94.0% | 0.28 | 6.7 | 1.46 | 2.6 |
| 10 | 50 | 0.0% | 6.0% | 94.0% | 0.0% | 100.0% | 1.02 | 86.2 | 0.78 | 3.5 |
| 11 | 50 | 0.0% | 10.0% | 90.0% | 0.0% | 100.0% | 1.12 | 69.0 | 1.58 | 7.2 |
| 12 | 50 | 0.0% | 10.0% | 90.0% | 2.0% | 100.0% | 1.10 | 34.0 | 0.96 | 4.2 |

## Last 150 cases

- coverage by templates + handlers: 8.7%
- accuracy of the stream: 100.0%
- large model alone accuracy (baseline for cheaper-rung cases, stream's own otherwise): 100.0%
- paired accuracy difference, stream minus large alone: +0.0 points, 95% bootstrap interval [+0.0, +0.0]

## E-17 verdict lines

- coverage below 30%? YES (8.7%)
- accuracy more than 2 points below the large model alone, beyond the interval (interval's upper end < -2)? NO
- refutation condition met: YES

## Intents

| intent | cases | rungs used (handler/template/large) | highest rung reached | handler agreement | template agreement |
| --- | --- | --- | --- | --- | --- |
| compute_total_cost | 49 | 0/43/6 | template | 1/5 discarded v2 | 9/9 active v2 |
| compute_remaining_money | 44 | 0/38/6 | template | 4/5 discarded v2 | 9/9 active v2 |
| compute_rate_of_change | 41 | 26/10/5 | template | 5/6 discarded v2 | 11/11 active v1 |
| compute_difference_between_counts | 38 | 0/23/15 | large | 3/5 discarded v2 | 4/5 discarded v2 |
| compute_difference_between_costs | 29 | 13/0/16 | large | 4/5 discarded v2 | 4/5 discarded v2 |
| compute_mean | 26 | 15/0/11 | large | 8/8 shadow v1 | 4/5 discarded v2 |
| compute_total_count | 20 | 9/3/8 | large | 4/5 discarded v2 | 4/5 discarded v2 |
| compute_mode | 19 | 6/3/10 | large | 9/10 shadow v1 | 11/12 shadow v1 |
| compute_range_of_values | 17 | 9/0/8 | large | 5/5 shadow v1 | 6/6 shadow v2 |
| find_maximum_count | 17 | 10/0/7 | large | 4/4 shadow v1 | 2/5 discarded v2 |
| compute_probability | 17 | 0/0/17 | large | 3/5 discarded v2 | 2/5 discarded v2 |
| find_minimum_count | 16 | 8/1/7 | large | 3/3 shadow v2 | 5/6 discarded v2 |
| compute_median | 13 | 1/3/9 | handler | 9/9 active v1 | 10/10 active v2 |
| compute_function_property | 13 | 4/2/7 | large | 6/6 shadow v1 | 8/8 shadow v1 |
| count_people_interviewed_no | 13 | 5/3/5 | large | 3/3 shadow v2 | 6/6 shadow v2 |
| check_function_property | 12 | 3/4/5 | large | 5/5 shadow v2 | 7/7 shadow v2 |
| find_start_time | 11 | 0/4/7 | large | none | 4/5 discarded v2 |
| compute_remaining_money_v3 | 11 | 0/0/11 | template | 7/7 shadow v2 | 9/9 active v2 |
| compute_fraction_of_total | 10 | 0/0/10 | large | 1/4 shadow v2 | 2/5 discarded v2 |
| compute_max_count | 9 | 0/0/9 | large | 6/6 shadow v1 | 0/5 discarded v2 |
| count_students_below_threshold | 9 | 0/0/9 | large | 3/4 shadow v2 | 2/5 discarded v2 |
| compute_total_money_raised | 9 | 0/5/4 | large | 3/3 shadow v2 | 7/7 shadow v2 |
| find_start_time_no | 9 | 3/0/6 | large | 3/3 shadow v1 | 4/4 shadow v2 |
| compute_difference_between_amounts | 9 | 0/3/6 | large | 3/3 shadow v2 | 8/8 shadow v1 |
| compute_remaining_money_v2 | 9 | 0/0/9 | large | 5/5 shadow v2 | 8/8 shadow v1 |
| count_bags_at_least | 6 | 0/0/6 | large | 2/3 shadow v1 | 0/4 shadow v2 |
| compute_difference_between_amounts_v2 | 6 | 0/0/6 | large | 3/3 shadow v1 | 5/5 shadow v1 |
| count_buildings_at_least | 5 | 0/0/5 | large | 2/2 shadow v1 | 0/4 shadow v1 |
| count_exact_value | 5 | 0/0/5 | large | 1/2 shadow v1 | 0/4 shadow v1 |
| count_flocks_exact_value | 4 | 0/0/4 | large | 0/1 shadow v1 | 1/3 shadow v1 |
| compute_minimum_count | 4 | 0/0/4 | large | 0/1 shadow v1 | 0/3 shadow v1 |
| find_maximum_rating_no | 4 | 0/0/4 | large | 1/1 shadow v1 | 2/3 shadow v1 |
| compute_total_stamps_wait | 4 | 0/0/4 | large | 1/1 shadow v1 | 1/3 shadow v1 |
| find_start_time_v3 | 4 | 0/0/4 | large | 0/1 shadow v1 | 1/3 shadow v1 |
| count_bottles_collected | 3 | 0/0/3 | large | 0/0 shadow v1 | 2/2 shadow v1 |
| count_people_interviewed | 3 | 0/0/3 | large | 0/0 shadow v1 | 0/2 shadow v1 |
| compute_total_articles_read | 3 | 0/0/3 | large | 0/0 shadow v1 | 2/2 shadow v1 |
| compute_total_calls_made | 3 | 0/0/3 | large | 0/0 shadow v1 | 2/2 shadow v1 |
| count_ponds_at_least | 3 | 0/0/3 | large | 0/0 shadow v1 | 0/2 shadow v1 |
| count_children_weighed_weight | 3 | 0/0/3 | large | 0/0 shadow v1 | 1/2 shadow v1 |
| find_maximum_score | 3 | 0/0/3 | large | 0/0 shadow v1 | 2/2 shadow v1 |
| compute_difference_between_values | 3 | 0/0/3 | large | 0/0 shadow v1 | 1/2 shadow v1 |
| count_tanks_fewer_than | 3 | 0/0/3 | large | 0/0 shadow v1 | 0/2 shadow v1 |
| count_strings_at_least | 3 | 0/0/3 | large | 0/0 shadow v1 | 0/2 shadow v1 |
| count_students_below_threshold_v2 | 3 | 0/0/3 | large | 0/0 shadow v1 | 0/2 shadow v1 |
| find_start_time_v5 | 3 | 0/0/3 | large | 0/0 shadow v1 | 0/2 shadow v1 |
| count_rating_exact_value | 2 | 0/0/2 | large | none | none |
| compute_gross_income | 2 | 0/0/2 | large | none | none |
| count_races_meeting_condition | 2 | 0/0/2 | large | none | none |
| compute_time_duration | 2 | 0/0/2 | large | none | none |
| compute_difference_between_weights | 2 | 0/0/2 | large | none | none |
| count_racks_at_least | 2 | 0/0/2 | large | none | none |
| compute_total_pearls_but | 2 | 0/0/2 | large | none | none |
| compute_total_people_in | 2 | 0/0/2 | large | none | none |
| count_teams_at_least | 2 | 0/0/2 | large | none | none |
| compute_total_cost_v2 | 2 | 0/0/2 | large | none | none |
| compute_gross_income_v2 | 2 | 0/0/2 | large | none | none |
| find_start_time_v4 | 2 | 0/0/2 | large | none | none |
| count_cars_in_stock | 1 | 0/0/1 | large | none | none |
| count_players_scored_touchdowns | 1 | 0/0/1 | large | none | none |
| count_farms_with_exact | 1 | 0/0/1 | large | none | none |
| count_students_exact_score | 1 | 0/0/1 | large | none | none |
| count_people_in_state | 1 | 0/0/1 | large | none | none |
| find_maximum_rating | 1 | 0/0/1 | large | none | none |
| count_restaurants_below_threshold | 1 | 0/0/1 | large | none | none |
| count_clubs_exact_value | 1 | 0/0/1 | large | none | none |
| count_stickers_in_collection | 1 | 0/0/1 | large | none | none |
| compare_patterns | 1 | 0/0/1 | large | none | none |
| count_companies_exact_value | 1 | 0/0/1 | large | none | none |
| count_wood_types_bookcases | 1 | 0/0/1 | large | none | none |
| compute_total_slices_sold | 1 | 0/0/1 | large | none | none |
| count_countries_exact_value | 1 | 0/0/1 | large | none | none |
| count_stores_exact_value | 1 | 0/0/1 | large | none | none |
| compute_total_frogs_in | 1 | 0/0/1 | large | none | none |
| find_start_time_v2 | 1 | 0/0/1 | large | none | none |
| count_passengers_per_train | 1 | 0/0/1 | large | none | none |
| count_employees_mailed_at | 1 | 0/0/1 | large | none | none |
| compare_patterns_no_it | 1 | 0/0/1 | large | none | none |
| compute_total_cost_v3 | 1 | 0/0/1 | large | none | none |
| compute_difference_between_counts_v2 | 1 | 0/0/1 | large | none | none |
| compute_total_cost_v4 | 1 | 0/0/1 | large | none | none |
| compute_total_cost_v5 | 1 | 0/0/1 | large | none | none |
| find_start_time_v6 | 1 | 0/0/1 | large | none | none |
| count_children_weighed_weight_v2 | 1 | 0/0/1 | large | none | none |
| count_bags_at_least_v2 | 1 | 0/0/1 | large | none | none |
| count_restaurants_below_threshold_v2 | 1 | 0/0/1 | large | none | none |
