# E-17 summary

450 cases, chunks of 50.

## Per chunk

| chunk | n | handler | template | large | fallback | accuracy | large calls/case | large s/case | small calls/case | small s/case |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 100 | 7.0% | 17.0% | 76.0% | 1.0% | 100.0% | 1.05 | 27.3 | 1.66 | 3.5 |
| 2 | 100 | 16.0% | 29.0% | 55.0% | 2.0% | 99.0% | 0.81 | 23.3 | 2.09 | 4.9 |
| 3 | 100 | 32.0% | 32.0% | 36.0% | 6.0% | 97.0% | 0.50 | 17.6 | 1.80 | 5.3 |
| 7 | 50 | 26.0% | 42.0% | 32.0% | 10.0% | 100.0% | 0.46 | 13.6 | 1.64 | 3.9 |
| 8 | 50 | 44.0% | 26.0% | 30.0% | 2.0% | 88.0% | 0.40 | 11.3 | 1.46 | 2.7 |
| 9 | 50 | 44.0% | 40.0% | 16.0% | 6.0% | 94.0% | 0.28 | 6.7 | 1.46 | 2.6 |

## Last 150 cases

- coverage by templates + handlers: 74.0%
- accuracy of the stream: 94.0%
- large model alone accuracy (baseline for cheaper-rung cases, stream's own otherwise): 99.3%
- paired accuracy difference, stream minus large alone: -5.3 points, 95% bootstrap interval [-9.3, -2.0]

## E-17 verdict lines

- coverage below 30%? NO (74.0%)
- accuracy more than 2 points below the large model alone, beyond the interval (interval's upper end < -2)? NO
- refutation condition met: NO

## Intents

| intent | cases | rungs used (handler/template/large) | highest rung reached | handler agreement | template agreement |
| --- | --- | --- | --- | --- | --- |
| compute_total_cost | 46 | 0/40/6 | template | 1/5 discarded v2 | 3/3 active v2 |
| compute_remaining_money | 41 | 0/35/6 | template | 4/5 discarded v2 | 3/3 active v2 |
| compute_rate_of_change | 35 | 26/5/4 | handler | 3/3 active v2 | 3/3 active v1 |
| compute_difference_between_counts | 35 | 0/23/12 | template | 3/5 discarded v2 | 3/3 active v1 |
| compute_difference_between_costs | 23 | 13/0/10 | handler | 3/3 active v2 | 4/5 discarded v2 |
| compute_mean | 21 | 15/0/6 | handler | 3/3 active v1 | 3/4 shadow v2 |
| compute_total_count | 17 | 9/3/5 | handler | 3/3 active v2 | 3/3 active v1 |
| find_minimum_count | 16 | 8/1/7 | handler | 3/3 active v2 | 3/3 active v2 |
| find_maximum_count | 16 | 10/0/6 | handler | 3/3 active v1 | 2/4 shadow v2 |
| compute_range_of_values | 15 | 9/0/6 | handler | 3/3 active v1 | 3/3 active v2 |
| count_people_interviewed_no | 13 | 5/3/5 | handler | 3/3 active v2 | 3/3 active v1 |
| compute_mode | 12 | 6/2/4 | handler | 3/3 active v1 | 3/3 active v1 |
| compute_probability | 12 | 0/0/12 | large | 3/5 discarded v2 | 2/5 discarded v2 |
| check_function_property | 11 | 3/4/4 | handler | 3/3 active v2 | 3/3 active v1 |
| find_start_time | 11 | 0/4/7 | template | none | 3/3 active v1 |
| compute_function_property | 10 | 4/2/4 | handler | 3/3 active v1 | 3/3 active v1 |
| count_students_below_threshold | 9 | 0/0/9 | handler | 3/3 active v1 | 2/5 discarded v2 |
| compute_total_money_raised | 9 | 0/5/4 | handler | 3/3 active v2 | 3/3 active v1 |
| find_start_time_no | 9 | 3/0/6 | handler | 3/3 active v1 | 3/3 active v2 |
| compute_fraction_of_total | 8 | 0/0/8 | large | 1/2 shadow v2 | 2/5 discarded v2 |
| compute_median | 7 | 1/2/4 | handler | 3/3 active v1 | 3/3 active v1 |
| compute_difference_between_amounts | 7 | 0/3/4 | template | 2/4 shadow v1 | 3/3 active v1 |
| compute_max_count | 5 | 0/0/5 | large | 2/2 shadow v1 | 0/4 shadow v1 |
| count_buildings_at_least | 5 | 0/0/5 | large | 2/2 shadow v1 | 0/4 shadow v1 |
| count_exact_value | 4 | 0/0/4 | large | 1/1 shadow v1 | 0/3 shadow v1 |
| count_people_interviewed | 3 | 0/0/3 | large | 0/0 shadow v1 | 1/2 shadow v1 |
| compute_minimum_count | 3 | 0/0/3 | large | 0/0 shadow v1 | 0/2 shadow v1 |
| find_maximum_rating_no | 3 | 0/0/3 | large | 0/0 shadow v1 | 1/2 shadow v1 |
| count_rating_exact_value | 2 | 0/0/2 | large | none | none |
| compute_gross_income | 2 | 0/0/2 | large | none | none |
| compute_time_duration | 2 | 0/0/2 | large | none | none |
| compute_total_calls_made | 2 | 0/0/2 | large | none | none |
| count_children_weighed_weight | 2 | 0/0/2 | large | none | none |
| find_maximum_score | 2 | 0/0/2 | large | none | none |
| compute_difference_between_values | 2 | 0/0/2 | large | none | none |
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
| count_tanks_fewer_than | 1 | 0/0/1 | large | none | none |
| count_teams_at_least | 1 | 0/0/1 | large | none | none |
| count_countries_exact_value | 1 | 0/0/1 | large | none | none |
| compute_total_stamps_wait | 1 | 0/0/1 | large | none | none |
| count_bags_at_least | 1 | 0/0/1 | large | none | none |
| count_stores_exact_value | 1 | 0/0/1 | large | none | none |
| count_strings_at_least | 1 | 0/0/1 | large | none | none |
| compute_total_frogs_in | 1 | 0/0/1 | large | none | none |
