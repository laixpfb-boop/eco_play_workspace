"""预留算法扩展模块 - 投票权重、舒适度评分等"""

from math import sqrt


def _pearson_correlation(xs, ys):
    if len(xs) < 2 or len(xs) != len(ys):
        return None

    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denominator_x = sqrt(sum((x - mean_x) ** 2 for x in xs))
    denominator_y = sqrt(sum((y - mean_y) ** 2 for y in ys))
    denominator = denominator_x * denominator_y
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _weighted_average(values, weights):
    total_weight = sum(weights)
    if total_weight <= 0:
        return None
    return sum(value * weight for value, weight in zip(values, weights)) / total_weight


def _weighted_std(values, weights, mean_value):
    total_weight = sum(weights)
    if total_weight <= 0:
        return None
    variance = sum(weight * ((value - mean_value) ** 2) for value, weight in zip(values, weights)) / total_weight
    return sqrt(max(variance, 0))

def calculate_weighted_comfort(building_votes, sensor_data=None, weights=None):
    """
    带权重的舒适度计算（可扩展）
    :param building_votes: 投票数据 dict (too_cold, comfort, too_warm, total)
    :param sensor_data: 传感器数据 dict (temperature, humidity)
    :param weights: 权重配置 dict (too_cold: float, comfort: float, too_warm: float, temp_factor: float)
    :return: 加权舒适度评分 float
    """
    # 默认权重
    default_weights = {
        'too_cold': -0.5,    # 过冷权重（负分）
        'comfort': 1.0,      # 舒适权重（正分）
        'too_warm': -0.3,    # 过热权重（负分）
        'temp_factor': 0.1   # 温度影响因子（可关联传感器）
    }
    w = weights or default_weights

    if building_votes['total'] <= 0:
        return 0.0
    
    # 基础评分（基于投票）
    base_score = (
        building_votes['too_cold'] * w['too_cold'] +
        building_votes['comfort'] * w['comfort'] +
        building_votes['too_warm'] * w['too_warm']
    ) / building_votes['total'] * 100
    
    # 传感器温度修正（可选扩展）
    if sensor_data:
        # 假设22-26℃是最佳温度，偏离则扣分
        ideal_temp = 24
        temp_diff = abs(sensor_data['temperature'] - ideal_temp)
        temp_penalty = temp_diff * w['temp_factor']
        base_score -= temp_penalty
    
    return round(base_score, 2)


def analyze_comfort_correlation(rows):
    """
    rows: list[dict] with
      building_id, building_name, vote_date, comfort_percent, total,
      avg_temperature, avg_humidity
    """
    if not rows:
        return {
            'sampleSize': 0,
            'correlations': {
                'temperature_to_comfort': None,
                'humidity_to_comfort': None,
            },
            'recommendation': {
                'temperature': None,
                'humidity': None,
            },
            'buildingRecommendations': [],
        }

    valid_temperature_rows = [row for row in rows if row.get('avg_temperature') is not None]
    valid_humidity_rows = [row for row in rows if row.get('avg_humidity') is not None]

    temperature_correlation = _pearson_correlation(
        [row['avg_temperature'] for row in valid_temperature_rows],
        [row['comfort_percent'] for row in valid_temperature_rows],
    )
    humidity_correlation = _pearson_correlation(
        [row['avg_humidity'] for row in valid_humidity_rows],
        [row['comfort_percent'] for row in valid_humidity_rows],
    )

    high_comfort_rows = sorted(rows, key=lambda row: (row['comfort_percent'], row['total']), reverse=True)
    cutoff = max(3, len(high_comfort_rows) // 3)
    top_rows = [row for row in high_comfort_rows[:cutoff] if row['total'] > 0]
    weights = [row['comfort_percent'] * row['total'] for row in top_rows]

    recommended_temperature = None
    recommended_temperature_range = None
    if top_rows and any(row.get('avg_temperature') is not None for row in top_rows):
        top_temperature_rows = [row for row in top_rows if row.get('avg_temperature') is not None]
        temp_values = [row['avg_temperature'] for row in top_temperature_rows]
        temp_weights = [row['comfort_percent'] * row['total'] for row in top_temperature_rows]
        temp_mean = _weighted_average(temp_values, temp_weights)
        if temp_mean is not None:
            temp_std = _weighted_std(temp_values, temp_weights, temp_mean) or 0.6
            recommended_temperature = round(temp_mean, 1)
            recommended_temperature_range = {
                'min': round(temp_mean - temp_std, 1),
                'max': round(temp_mean + temp_std, 1),
            }

    recommended_humidity = None
    recommended_humidity_range = None
    if top_rows and any(row.get('avg_humidity') is not None for row in top_rows):
        top_humidity_rows = [row for row in top_rows if row.get('avg_humidity') is not None]
        humidity_values = [row['avg_humidity'] for row in top_humidity_rows]
        humidity_weights = [row['comfort_percent'] * row['total'] for row in top_humidity_rows]
        humidity_mean = _weighted_average(humidity_values, humidity_weights)
        if humidity_mean is not None:
            humidity_std = _weighted_std(humidity_values, humidity_weights, humidity_mean) or 3.0
            recommended_humidity = round(humidity_mean, 1)
            recommended_humidity_range = {
                'min': round(humidity_mean - humidity_std, 1),
                'max': round(humidity_mean + humidity_std, 1),
            }

    building_recommendations = []
    grouped = {}
    for row in rows:
        grouped.setdefault(row['building_id'], []).append(row)

    for building_rows in grouped.values():
        ranked_rows = sorted(building_rows, key=lambda row: (row['comfort_percent'], row['total']), reverse=True)
        best_row = ranked_rows[0]
        building_recommendations.append({
            'building_id': best_row['building_id'],
            'building_name': best_row['building_name'],
            'best_vote_date': best_row['vote_date'],
            'comfort_percent': best_row['comfort_percent'],
            'temperature': round(best_row['avg_temperature'], 1) if best_row.get('avg_temperature') is not None else None,
            'humidity': round(best_row['avg_humidity'], 1) if best_row.get('avg_humidity') is not None else None,
        })

    building_recommendations.sort(key=lambda row: row['comfort_percent'], reverse=True)

    return {
        'sampleSize': len(rows),
        'correlations': {
            'temperature_to_comfort': temperature_correlation,
            'humidity_to_comfort': humidity_correlation,
        },
        'recommendation': {
            'temperature': recommended_temperature,
            'temperature_range': recommended_temperature_range,
            'humidity': recommended_humidity,
            'humidity_range': recommended_humidity_range,
        },
        'buildingRecommendations': building_recommendations,
    }
