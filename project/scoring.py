import inspect
import warnings
from functools import partial
import datetime
from datetime import date
from django.db.models import Sum, Count, F, Max
from django.apps import apps


now = datetime.datetime.now()
this_year = now.year
last_day = date(this_year,12,31)
today = date.today()

days_diff = today - last_day
days_left = days_diff.days
#print(abs(days_left.days))

## Pull performance from GCP
L90Revenue = 17790255
forecast = L90Revenue/90 * days_left

## Pull from Goals table new model
goal=350000000
goal_gap = goal-forecast

## pull from Projects table
highest_active_score = 45000 # Unable to import project model ?? Project.objects.filter(approved = True).aggregate(Max('score'))

## Pull from Goals table new model
ic_goal = 360000
ic_forecast = 300000
ic_weight = ic_forecast/ic_goal

ips_goal = 550
ips_forecast = 475
ips_weight = ips_forecast/ips_goal

ipf_goal = 1.51
ipf_forecast = 1.18
ipf_weight = ipf_forecast/ipf_goal


class BvmScore():

    def __init__(self, project_value, loe, v3co_score_selection, adl_score_strength, adl_score_purpose, strategy_level):
        # BVM Elements
        self.project_value = project_value
        self.loe = loe
        self.v3co_score_selection = v3co_score_selection
        self.adl_score_strength = adl_score_strength
        self.adl_score_purpose = adl_score_purpose
        self.strategy_level = strategy_level


    def score_project(self):
        # BVM Element Score Mapping
        loe_dict = {"NA":0, "XXL":100, "XL":200, "L":300,"M":400,"S":500,"XS":600}
        v3co_importance = {"ic_weight":ic_weight, "ips_weight":ips_weight, "ipf_weight":ipf_weight} #recode to be dynamic
        v3co_score_dict = {"IC":v3co_importance["ic_weight"], "IPS":v3co_importance["ips_weight"], "IPF":v3co_importance["ipf_weight"]}
        strategy_level_dict = {"Corporate":100,"Business Unit":60,"Team":30}
        purpose_dict = {"New Growth":100.0, "Hold Position":90.0, "Defend Position":80.0, "Reverse Decay":70.0}
        viability_dict = {"Strong":100.0, "Able":90.0, "Attainable":80.0, "Steep Climb":70.0, }
        

        # BVM Element Score
        adl_purpose = purpose_dict[self.adl_score_purpose]
        adl_viability = viability_dict[self.adl_score_strength]
        v3co_score = v3co_score_dict[self.v3co_score_selection]
        strategy_level_score = strategy_level_dict[self.strategy_level]
        loe_score = loe_dict[self.loe]
        project_value_score = (self.project_value/goal_gap*1000)
        adl_score = adl_viability * adl_purpose

        # Executing Weighting
        projectvalue_weight = 1
        loe_weight = 0.9
        v3co_score_weight = 0.5
        adl_score_weight = 0.6
        strategy_level_weight = 1

        # BVM Weighted Score
        bvm_weighted_score = (
        v3co_score * v3co_score_weight +
        strategy_level_score * strategy_level_weight +
        loe_score * loe_weight +
        project_value_score * projectvalue_weight +
        adl_score * adl_score_weight
        )

        return bvm_weighted_score

    def prioritize(self,bvm_weighted_score,highest_active_score):
        if highest_active_score < bvm_weighted_score:
            highest_active_score = bvm_weighted_score
            priority_score = bvm_weighted_score/highest_active_score*100
        else:
            priority_score = bvm_weighted_score/highest_active_score*100

        return priority_score

if __name__ == "__main__":

    #print(bvm_weighted_score, prioritize(bvm_weighted_score,highest_active_score))

    #project = BvmScore(110000000,"XS","IPF",50,100,"Business Unit")
    project = BvmScore(project_value, loe, v3co_score_selection, adl_score_strength, adl_score_purpose, strategy_level)
    score = project.score_project()
    print(score, project.prioritize(score,highest_active_score))
