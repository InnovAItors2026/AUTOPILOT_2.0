# AUTOPILOT 2.0 – Resilient Supply Chain Management

**An intelligent supply chain resilience and disruption management system.**

## 1. Project Overview

AUTOPILOT 2.0 is a supply chain resilience prototype designed to identify supplier risks, analyse the impact of disruptions, simulate cascading failures, and support faster recovery decisions.

Modern supply chains involve multiple suppliers, factories, warehouses, transportation routes, and customer orders. A disruption at one supplier can affect several connected entities, resulting in material shortages, production challenges, and potential delivery delays.

AUTOPILOT 2.0 aims to provide a digital representation of the supply chain and analyse these dependencies to help organisations understand potential disruptions and make informed recovery decisions.

## 2. Problem Statement

Traditional supply chain management systems may not provide sufficient visibility into multi-tier supplier dependencies and the cascading effects of disruptions.

When a supplier experiences a disruption, organisations need to identify:
- Which materials and suppliers are affected?
- Which factories and warehouses may experience shortages?
- Which customer orders are exposed?
- Are alternative suppliers available?
- What recovery strategies can minimise disruption?

AUTOPILOT 2.0 addresses these challenges through supply chain modelling, risk analysis, disruption simulation, and recovery planning.

## 3. Project Objectives

- Build a digital twin of the multi-tier supply chain.
- Identify critical and high-risk suppliers.
- Analyse the impact of single and multiple supplier disruptions.
- Identify affected materials, factories, warehouses, routes, and customer orders.
- Evaluate backup supplier availability and capacity.
- Simulate cascading failures across the supply chain.
- Recommend suitable recovery strategies.
- Provide an integrated interface for monitoring and analysing supply chain disruptions.
- Explore future SAP integration.

## 4. Solution Architecture

The proposed system follows this workflow:

```text
       Supply Chain Dataset
                |
                v
       Data Management
                |
                v
       Supply Chain Digital Twin
                |
                v
       Supplier Risk Analysis
                |
                v
       Disruption Impact Analysis
                |
                v
       Cascading Failure Simulation
                |
                v
       Recovery Optimisation
                |
                v
       Frontend Dashboard
                |
                v
       Supply Chain Resilience Insights
```

## 5. Team Responsibilities

The project is divided among five members.

### Member 1 – Data Management & Supply Chain Digital Twin

**Responsibility:** Build the data foundation.

- Prepare supplier, material, factory, warehouse, and customer-order datasets.
- Create the common data structure.
- Connect Tier-1, Tier-2, and Tier-3 suppliers.
- Build the supply chain dependency network using NetworkX.
- Identify shared upstream supplier dependencies.
- Provide datasets and graph functions to other modules.

### Member 2 – Supplier Risk & Disruption Impact Analysis

**Responsibility:** Identify supplier risks and analyse disruption impacts.

- Identify critical and high-risk suppliers.
- Calculate supplier risk scores and categories.
- Accept single and multiple supplier disruption inputs.
- Identify failed suppliers and affected materials.
- Find downstream suppliers and potential cascading exposure.
- Analyse available inventory and backup supplier capacity.
- Identify affected factories, warehouses, transportation routes, and customer orders.
- Estimate potential financial exposure.
- Generate explainable disruption impact reports.

**Implemented:** Supplier risk scoring, single-supplier disruption analysis, and multi-supplier disruption simulation with overlap analysis.

**Current data limitations:** Production days remaining and delivery delays are marked NOT COMPUTED because the required consumption, production, and shipment schedule data is unavailable.

### Member 3 – Backup Supplier Intelligence & Recovery Optimisation

**Responsibility:** Identify alternative suppliers and optimise recovery decisions.

- Analyse alternative and backup suppliers.
- Evaluate supplier availability and capacity.
- Identify suitable replacement suppliers.
- Develop recovery strategies.
- Compare recovery options based on cost, delivery delays, shortages, and fulfilment.
- Support recovery optimisation.

### Member 4 – Cascading Failure Simulation & Recovery Plan Challenger

**Responsibility:** Analyse supply chain-wide disruption propagation.

- Simulate cascading failures across multiple supply chain levels.
- Identify interconnected supplier dependencies.
- Analyse the propagation of disruptions.
- Evaluate the impact of combined failures.
- Challenge and assess proposed recovery plans.
- Identify vulnerabilities in recovery strategies.

### Member 5 – Frontend, Integration & SAP Preparation

**Responsibility:** Integrate the modules and provide the user interface.

- Develop the frontend dashboard.
- Integrate the outputs from all team members.
- Display supplier risks and disruption alerts.
- Visualise the supply chain network.
- Present disruption impact and recovery results.
- Prepare the system for potential SAP integration.

## 6. Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core development |
| Pandas | Dataset handling and analysis |
| NetworkX | Supply chain dependency graph |
| CSV | Initial dataset storage |
| Git & GitHub | Version control and collaboration |
| Frontend technologies | Dashboard development and integration |

Additional technologies may be incorporated as the project modules evolve.

## 7. Project Structure

```text
AUTOPILOT_2.0/
│
├── data/
│   ├── suppliers.csv
│   ├── materials.csv
│   ├── factories