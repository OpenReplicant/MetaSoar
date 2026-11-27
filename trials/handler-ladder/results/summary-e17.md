# E-17 summary

300 cases, chunks of 100.

## Per chunk

| chunk | n | handler | template | large | fallback | accuracy | large calls/case | large s/case | small calls/case | small s/case |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 100 | 7.0% | 17.0% | 76.0% | 1.0% | 100.0% | 1.05 | 27.3 | 1.66 | 3.5 |
| 2 | 100 | 16.0% | 29.0% | 55.0% | 2.0% | 99.0% | 0.81 | 23.3 | 2.09 | 4.9 |
| 3 | 100 | 32.0% | 32.0% | 36.0% | 6.0% | 97.0% | 0.50 | 17.6 | 1.80 | 5.3 |

## Last 150 cases

- coverage by templates + handlers: 58.7%
- accuracy of the stream: 98.0%
- large model alone accuracy (baseline for cheaper-rung cases, stream's own otherwise): 99.3%
- paired accuracy difference, stream minus large alone: -1.3 points, 95% bootstrap interval [-3.3, +0.0]

## E-17 verdict lines

- coverage below 30%? NO (58.7%)
- accuracy more than 2 points below the large model alone, beyond the interval (interval's upper end < -2)? NO
- refutation condition met: NO

## Intents

| intent | cases | rungs used (handler/template/large) | highest rung reached | handler agreement | template agreement |
| --- | --- | --- | --- | --- | --- |
| compute_total_cost | 32 | 0/26/6 | template | 1/5 discarded v2 | 3/3 active v2 |
| compute_rate_of_change | 30 | 21/5/4 | handler | 3/3 active v2 | 3/3 active v1 |
| compute_remaining_money | 25 | 0/19/6 | template | 4/5 discarded v2 | 3/3 active v2 |
| compute_difference_between_counts | 24 | 0/13/11 | template | 3/5 discarded v2 | 3/3 active v1 |
| compute_difference_between_costs | 20 | 11/0/9 | handler | 3/3 active v2 | 4/5 discarded v2 |
| compute_mean | 14 | 8/0/6 | handler | 3/3 active v1 | 3/4 shadow v2 |
| find_maximum_count | 11 | 5/0/6 | handler | 3/3 active v1 | 2/4 shadow v2 |
| compute_mode | 11 | 5/2/4 | handler | 3/3 active v1 | 3/3 active v1 |
| find_minimum_count | 9 | 1/1/7 | handler | 3/3 active v2 | 3/3 active v2 |
| compute_range_of_values | 9 | 3/0/6 | handler | 3/3 active v1 | 3/3 active v2 |
| compute_probability | 8 | 0/0/8 | large | 2/2 shadow v2 | 2/5 discarded v2 |
| compute_function_property | 7 | 1/2/4 | handler | 3/3 active v1 | 3/3 active v1 |
| count_people_interviewed_no | 7 | 0/2/5 | template | 3/4 shadow v1 | 3/3 active v1 |
| check_function_property | 6 | 0/2/4 | template | 2/3 shadow v1 | 3/3 active v1 |
| compute_median | 6 | 0/2/4 | handler | 3/3 active v1 | 3/3 active v1 |
| count_students_below_threshold | 6 | 0/0/6 | handler | 3/3 active v1 | 2/4 shadow v2 |
| compute_total_count | 6 | 0/2/4 | template | 2/3 shadow v1 | 3/3 active v1 |
| compute_fraction_of_total | 6 | 0/0/6 | large | 1/3 shadow v1 | 2/4 shadow v2 |
| find_start_time | 5 | 0/1/4 | template | none | 3/3 active v1 |
| compute_total_money_raised | 5 | 0/1/4 | template | 0/2 shadow v1 | 3/3 active v1 |
| compute_max_count | 4 | 0/0/4 | large | 1/1 shadow v1 | 0/3 shadow v1 |
| find_start_time_no | 4 | 0/0/4 | large | 1/1 shadow v1 | 2/3 shadow v1 |
| count_people_interviewed | 3 | 0/0/3 | large | 0/0 shadow v1 | 1/2 shadow v1 |
| count_buildings_at_least | 3 | 0/0/3 | large | 0/0 shadow v1 | 0/2 shadow v1 |
| compute_minimum_count | 3 | 0/0/3 | large | 0/0 shadow v1 | 0/2 shadow v1 |
| count_exact_value | 3 | 0/0/3 | large | 0/0 shadow v1 | 0/2 shadow v1 |
| count_rating_exact_value | 2 | 0/0/2 | large | none | none |
| compute_gross_income | 2 | 0/0/2 | large | none | none |
| compute_time_duration | 2 | 0/0/2 | large | none | none |
| compute_total_calls_made | 2 | 0/0/2 | large | none | none |
| count_children_weighed_weight | 2 | 0/0/2 | large | none | none |
| count_bottles_collected | 1 | 0/0/1 | large | none | none |
| count_cars_in_stock | 1 | 0/0/1 | large | none | none |
| count_races_meeting_condition | 1 | 0/0/1 | large | none | none |
| compute_total_articles_read | 1 | 0/0/1 | large | none | none |
| count_players_scored_touchdowns | 1 | 0/0/1 | large | none | none |
| compute_difference_between_weights | 1 | 0/0/1 | large | none | none |
| count_farms_with_exact | 1 | 0/0/1 | large | none | none |
| count_students_exact_score | 1 | 0/0/1 | large | none | none |
| count_people_in_state | 1 | 0/0/1 | large | none | none |
| find_maximum_rating | 1 | 0/0/1 | large | none | none |
| count_restaurants_below_threshold | 1 | 0/0/1 | large | none | none |
| count_flocks_exact_value | 1 | 0/0/1 | large | none | none |
| count_racks_at_least | 1 | 0/0/1 | large | none | none |
| count_ponds_at_least | 1 | 0/0/1 | large | none | none |
| count_clubs_exact_value | 1 | 0/0/1 | large | none | none |
| count_stickers_in_collection | 1 | 0/0/1 | large | none | none |
| compute_total_pearls_but | 1 | 0/0/1 | large | none | none |
| compare_patterns | 1 | 0/0/1 | large | none | none |
| count_companies_exact_value | 1 | 0/0/1 | large | none | none |
| count_wood_types_bookcases | 1 | 0/0/1 | large | none | none |
| compute_total_people_in | 1 | 0/0/1 | large | none | none |
| compute_total_slices_sold | 1 | 0/0/1 | large | none | none |
| find_maximum_score | 1 | 0/0/1 | large | none | none |
