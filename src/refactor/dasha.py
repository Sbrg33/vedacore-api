#!/usr/bin/env python3
"""
Vimshottari Dasha period calculations for KP astrology.
120-year cycle of planetary periods with nested sub-periods.

This module provides high-precision calculations for:
- Mahadasha (major periods)
- Antardasha (sub-periods)
- Pratyantardasha (sub-sub-periods)
- Sookshma (sub-sub-sub-periods)
- Prana (sub-sub-sub-sub-periods)
"""

import logging

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import swisseph as swe

from refactor.time_utils import validate_utc_datetime

logger = logging.getLogger(__name__)

# Nakshatra to Dasha lord mapping (1-27)
NAKSHATRA_LORDS = {
    1: "Ketu",
    2: "Venus",
    3: "Sun",
    4: "Moon",
    5: "Mars",
    6: "Rahu",
    7: "Jupiter",
    8: "Saturn",
    9: "Mercury",
    10: "Ketu",
    11: "Venus",
    12: "Sun",
    13: "Moon",
    14: "Mars",
    15: "Rahu",
    16: "Jupiter",
    17: "Saturn",
    18: "Mercury",
    19: "Ketu",
    20: "Venus",
    21: "Sun",
    22: "Moon",
    23: "Mars",
    24: "Rahu",
    25: "Jupiter",
    26: "Saturn",
    27: "Mercury",
}

# Dasha sequence order (starts from birth nakshatra lord)
DASHA_SEQUENCE = [
    "Ketu",
    "Venus",
    "Sun",
    "Moon",
    "Mars",
    "Rahu",
    "Jupiter",
    "Saturn",
    "Mercury",
]

# Vimshottari period years for each planet
VIMSHOTTARI_YEARS = {
    "Ketu": 7,
    "Venus": 20,
    "Sun": 6,
    "Moon": 10,
    "Mars": 7,
    "Rahu": 18,
    "Jupiter": 16,
    "Saturn": 19,
    "Mercury": 17,
}

# Total cycle duration in years
TOTAL_CYCLE_YEARS = 120

# Days per year for high-precision calculations
DAYS_PER_YEAR = Decimal("365.25")


@dataclass
class DashaPeriod:
    """Represents a Dasha period at any level"""

    level: str  # 'mahadasha', 'antardasha', 'pratyantardasha', 'sookshma', 'prana'
    planet: str
    start_date: datetime
    end_date: datetime
    duration_days: Decimal
    sub_periods: list["DashaPeriod"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "level": self.level,
            "planet": self.planet,
            "start": self.start_date.isoformat(),
            "end": self.end_date.isoformat(),
            "duration_days": float(self.duration_days),
            "sub_periods": [sp.to_dict() for sp in self.sub_periods],
        }

    def is_active(self, reference_time: datetime | None = None) -> bool:
        """Check if period is active at given time"""
        if reference_time is None:
            reference_time = datetime.utcnow()
        return self.start_date <= reference_time < self.end_date


class VimshottariDashaEngine:
    """
    High-precision Vimshottari Dasha calculator using Swiss Ephemeris.
    Ensures 100% accuracy with legacy master_ephe implementation.
    """

    def __init__(self, ephe_path: str = "./swisseph/ephe"):
        """
        Initialize Vimshottari Dasha calculator.

        Args:
            ephe_path: Path to Swiss Ephemeris data files
        """
        swe.set_ephe_path(ephe_path)
        # Set sidereal mode to Krishnamurti ayanamsa
        swe.set_sid_mode(5)  # KP ayanamsa
        self.total_cycle_years = Decimal(str(TOTAL_CYCLE_YEARS))
        logger.info("VimshottariDashaEngine initialized with KP ayanamsa")

    def get_moon_longitude(self, ts_utc: datetime) -> float:
        """
        Get Moon's sidereal longitude at given time.

        Args:
            ts_utc: UTC timestamp

        Returns:
            Moon's sidereal longitude in degrees (0-360)
        """
        ts_utc = validate_utc_datetime(ts_utc)
        jd = swe.julday(
            ts_utc.year,
            ts_utc.month,
            ts_utc.day,
            ts_utc.hour + ts_utc.minute / 60.0 + ts_utc.second / 3600.0,
        )

        # Get Moon position (planet ID 1 in Swiss Ephemeris)
        result = swe.calc_ut(jd, 1, swe.FLG_SIDEREAL)
        moon_longitude = result[0][0]  # Sidereal longitude

        return moon_longitude

    def get_nakshatra_from_longitude(self, longitude: float) -> tuple[int, str, float]:
        """
        Calculate nakshatra and its lord from longitude.

        Args:
            longitude: Sidereal longitude in degrees (0-360)

        Returns:
            Tuple of (nakshatra_number, nakshatra_lord, elapsed_portion)
        """
        # Each nakshatra spans 13.333... degrees (360/27)
        nakshatra_span = 360.0 / 27.0

        # Calculate nakshatra (1-27)
        nakshatra = int(longitude / nakshatra_span) + 1
        if nakshatra > 27:
            nakshatra = 27

        # Get ruling planet
        lord = NAKSHATRA_LORDS[nakshatra]

        # Calculate elapsed portion within nakshatra (0-1)
        nakshatra_start = (nakshatra - 1) * nakshatra_span
        elapsed_degrees = longitude - nakshatra_start
        elapsed_portion = elapsed_degrees / nakshatra_span

        return nakshatra, lord, elapsed_portion

    def calculate_birth_balance(
        self, birth_time: datetime, moon_longitude: float | None = None
    ) -> tuple[str, Decimal, Decimal]:
        """
        Calculate birth balance dasha (remaining period at birth).

        Args:
            birth_time: Birth UTC timestamp
            moon_longitude: Pre-calculated Moon longitude (optional)

        Returns:
            Tuple of (birth_lord, elapsed_days, remaining_days)
        """
        if moon_longitude is None:
            moon_longitude = self.get_moon_longitude(birth_time)

        nakshatra, lord, elapsed_portion = self.get_nakshatra_from_longitude(
            moon_longitude
        )

        # Total years for this lord's dasha
        lord_years = Decimal(str(VIMSHOTTARI_YEARS[lord]))
        lord_days = lord_years * DAYS_PER_YEAR

        # Calculate elapsed and remaining
        elapsed_days = lord_days * Decimal(str(elapsed_portion))
        remaining_days = lord_days - elapsed_days

        logger.debug(
            f"Birth nakshatra: {nakshatra}, Lord: {lord}, "
            f"Elapsed: {float(elapsed_portion):.4f}"
        )

        return lord, elapsed_days, remaining_days

    def generate_mahadashas(
        self,
        birth_time: datetime,
        moon_longitude: float | None = None,
        years_forward: int = 120,
    ) -> list[DashaPeriod]:
        """
        Generate Mahadasha periods from birth.

        Args:
            birth_time: Birth UTC timestamp
            moon_longitude: Pre-calculated Moon longitude (optional)
            years_forward: Number of years to calculate forward

        Returns:
            List of Mahadasha periods
        """
        birth_time = validate_utc_datetime(birth_time)

        # Get birth balance
        birth_lord, elapsed_days, remaining_days = self.calculate_birth_balance(
            birth_time, moon_longitude
        )

        mahadashas = []

        # Find starting position in sequence
        start_index = DASHA_SEQUENCE.index(birth_lord)

        # First mahadasha (partial - only remaining portion)
        current_start = birth_time - timedelta(days=float(elapsed_days))
        current_end = birth_time + timedelta(days=float(remaining_days))

        first_dasha = DashaPeriod(
            level="mahadasha",
            planet=birth_lord,
            start_date=current_start,
            end_date=current_end,
            duration_days=elapsed_days + remaining_days,
        )
        mahadashas.append(first_dasha)

        # Calculate subsequent mahadashas
        current_index = start_index
        current_date = current_end
        end_date = birth_time + timedelta(days=years_forward * 365.25)

        while current_date < end_date:
            # Move to next planet in sequence
            current_index = (current_index + 1) % 9
            planet = DASHA_SEQUENCE[current_index]

            # Full period for this planet
            years = Decimal(str(VIMSHOTTARI_YEARS[planet]))
            days = years * DAYS_PER_YEAR

            period_end = current_date + timedelta(days=float(days))

            dasha = DashaPeriod(
                level="mahadasha",
                planet=planet,
                start_date=current_date,
                end_date=period_end,
                duration_days=days,
            )
            mahadashas.append(dasha)

            current_date = period_end

        return mahadashas

    def calculate_antardashas(self, mahadasha: DashaPeriod) -> list[DashaPeriod]:
        """
        Calculate Antardasha (sub-periods) within a Mahadasha.

        Args:
            mahadasha: The Mahadasha period

        Returns:
            List of Antardasha periods
        """
        antardashas = []

        # Starting planet is the mahadasha lord
        start_index = DASHA_SEQUENCE.index(mahadasha.planet)
        current_date = mahadasha.start_date

        # Each planet gets proportional time based on its years
        for i in range(9):
            planet_index = (start_index + i) % 9
            planet = DASHA_SEQUENCE[planet_index]

            # Antardasha duration = (planet_years / 120) * mahadasha_days
            planet_years = Decimal(str(VIMSHOTTARI_YEARS[planet]))
            ratio = planet_years / self.total_cycle_years
            duration_days = mahadasha.duration_days * ratio

            period_end = current_date + timedelta(days=float(duration_days))

            antardasha = DashaPeriod(
                level="antardasha",
                planet=planet,
                start_date=current_date,
                end_date=period_end,
                duration_days=duration_days,
            )
            antardashas.append(antardasha)

            current_date = period_end

        return antardashas

    def calculate_pratyantar(self, antardasha: DashaPeriod) -> list[DashaPeriod]:
        """
        Calculate Pratyantardasha (sub-sub-periods) within an Antardasha.

        Args:
            antardasha: The Antardasha period

        Returns:
            List of Pratyantardasha periods
        """
        pratyantars = []

        # Starting planet is the antardasha lord
        start_index = DASHA_SEQUENCE.index(antardasha.planet)
        current_date = antardasha.start_date

        for i in range(9):
            planet_index = (start_index + i) % 9
            planet = DASHA_SEQUENCE[planet_index]

            # Pratyantar duration = (planet_years / 120) * antardasha_days
            planet_years = Decimal(str(VIMSHOTTARI_YEARS[planet]))
            ratio = planet_years / self.total_cycle_years
            duration_days = antardasha.duration_days * ratio

            period_end = current_date + timedelta(days=float(duration_days))

            pratyantar = DashaPeriod(
                level="pratyantardasha",
                planet=planet,
                start_date=current_date,
                end_date=period_end,
                duration_days=duration_days,
            )
            pratyantars.append(pratyantar)

            current_date = period_end

        return pratyantars

    def calculate_sookshma(self, pratyantar: DashaPeriod) -> list[DashaPeriod]:
        """
        Calculate Sookshma dasha (sub-sub-sub-periods).

        Args:
            pratyantar: The Pratyantardasha period

        Returns:
            List of Sookshma periods
        """
        sookshmas = []

        start_index = DASHA_SEQUENCE.index(pratyantar.planet)
        current_date = pratyantar.start_date

        for i in range(9):
            planet_index = (start_index + i) % 9
            planet = DASHA_SEQUENCE[planet_index]

            planet_years = Decimal(str(VIMSHOTTARI_YEARS[planet]))
            ratio = planet_years / self.total_cycle_years
            duration_days = pratyantar.duration_days * ratio

            period_end = current_date + timedelta(days=float(duration_days))

            sookshma = DashaPeriod(
                level="sookshma",
                planet=planet,
                start_date=current_date,
                end_date=period_end,
                duration_days=duration_days,
            )
            sookshmas.append(sookshma)

            current_date = period_end

        return sookshmas

    def calculate_prana(self, sookshma: DashaPeriod) -> list[DashaPeriod]:
        """
        Calculate Prana dasha (sub-sub-sub-sub-periods).

        Args:
            sookshma: The Sookshma period

        Returns:
            List of Prana periods
        """
        pranas = []

        start_index = DASHA_SEQUENCE.index(sookshma.planet)
        current_date = sookshma.start_date

        for i in range(9):
            planet_index = (start_index + i) % 9
            planet = DASHA_SEQUENCE[planet_index]

            planet_years = Decimal(str(VIMSHOTTARI_YEARS[planet]))
            ratio = planet_years / self.total_cycle_years
            duration_days = sookshma.duration_days * ratio

            period_end = current_date + timedelta(days=float(duration_days))

            prana = DashaPeriod(
                level="prana",
                planet=planet,
                start_date=current_date,
                end_date=period_end,
                duration_days=duration_days,
            )
            pranas.append(prana)

            current_date = period_end

        return pranas

    def get_current_dashas(
        self,
        birth_time: datetime,
        reference_time: datetime | None = None,
        levels: int = 3,
        moon_longitude: float | None = None,
    ) -> dict[str, DashaPeriod]:
        """
        Get currently active Dasha periods at specified levels.

        Args:
            birth_time: Birth UTC timestamp
            reference_time: Time to check (default: now)
            levels: Number of levels to calculate (1-5)
            moon_longitude: Pre-calculated Moon longitude (optional)

        Returns:
            Dict with active periods at each level
        """
        birth_time = validate_utc_datetime(birth_time)

        if reference_time is None:
            reference_time = datetime.utcnow()
        else:
            reference_time = validate_utc_datetime(reference_time)

        if levels < 1 or levels > 5:
            raise ValueError("Levels must be between 1 and 5")

        result = {}

        # Calculate mahadashas
        mahadashas = self.generate_mahadashas(birth_time, moon_longitude)

        # Find active mahadasha
        for maha in mahadashas:
            if maha.is_active(reference_time):
                result["mahadasha"] = maha

                if levels >= 2:
                    # Calculate and find active antardasha
                    antardashas = self.calculate_antardashas(maha)
                    for antar in antardashas:
                        if antar.is_active(reference_time):
                            result["antardasha"] = antar

                            if levels >= 3:
                                # Calculate and find active pratyantar
                                pratyantars = self.calculate_pratyantar(antar)
                                for pratyantar in pratyantars:
                                    if pratyantar.is_active(reference_time):
                                        result["pratyantardasha"] = pratyantar

                                        if levels >= 4:
                                            # Calculate and find active sookshma
                                            sookshmas = self.calculate_sookshma(
                                                pratyantar
                                            )
                                            for sookshma in sookshmas:
                                                if sookshma.is_active(reference_time):
                                                    result["sookshma"] = sookshma

                                                    if levels >= 5:
                                                        # Calculate and find active prana
                                                        pranas = self.calculate_prana(
                                                            sookshma
                                                        )
                                                        for prana in pranas:
                                                            if prana.is_active(
                                                                reference_time
                                                            ):
                                                                result["prana"] = prana
                                                                break
                                                    break
                                        break
                            break
                break

        return result

    def get_dasha_changes(
        self,
        date_utc: datetime,
        birth_time: datetime,
        moon_longitude: float | None = None,
        levels: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Get all dasha changes occurring on a specific date.

        Args:
            date_utc: Date to check for changes
            birth_time: Birth UTC timestamp
            moon_longitude: Pre-calculated Moon longitude (optional)
            levels: Number of levels to check (1-5)

        Returns:
            List of dasha change events
        """
        changes = []

        # Set date boundaries (00:00 to 23:59:59 UTC)
        day_start = datetime(date_utc.year, date_utc.month, date_utc.day, 0, 0, 0)
        day_end = day_start + timedelta(days=1) - timedelta(seconds=1)

        # Get mahadashas
        mahadashas = self.generate_mahadashas(birth_time, moon_longitude)

        # Check each level for changes
        for maha in mahadashas:
            # Check mahadasha changes
            if day_start <= maha.start_date <= day_end:
                changes.append(
                    {
                        "level": "mahadasha",
                        "type": "start",
                        "planet": maha.planet,
                        "timestamp": maha.start_date.isoformat(),
                    }
                )
            if day_start <= maha.end_date <= day_end:
                changes.append(
                    {
                        "level": "mahadasha",
                        "type": "end",
                        "planet": maha.planet,
                        "timestamp": maha.end_date.isoformat(),
                    }
                )

            if (
                levels >= 2
                and maha.start_date <= day_end
                and maha.end_date >= day_start
            ):
                # Check antardasha changes within active mahadasha
                antardashas = self.calculate_antardashas(maha)
                for antar in antardashas:
                    if day_start <= antar.start_date <= day_end:
                        changes.append(
                            {
                                "level": "antardasha",
                                "type": "start",
                                "planet": antar.planet,
                                "timestamp": antar.start_date.isoformat(),
                                "parent": maha.planet,
                            }
                        )
                    if day_start <= antar.end_date <= day_end:
                        changes.append(
                            {
                                "level": "antardasha",
                                "type": "end",
                                "planet": antar.planet,
                                "timestamp": antar.end_date.isoformat(),
                                "parent": maha.planet,
                            }
                        )

                    if (
                        levels >= 3
                        and antar.start_date <= day_end
                        and antar.end_date >= day_start
                    ):
                        # Check pratyantar changes
                        pratyantars = self.calculate_pratyantar(antar)
                        for pratyantar in pratyantars:
                            if day_start <= pratyantar.start_date <= day_end:
                                changes.append(
                                    {
                                        "level": "pratyantardasha",
                                        "type": "start",
                                        "planet": pratyantar.planet,
                                        "timestamp": pratyantar.start_date.isoformat(),
                                        "parent": f"{maha.planet}-{antar.planet}",
                                    }
                                )
                            if day_start <= pratyantar.end_date <= day_end:
                                changes.append(
                                    {
                                        "level": "pratyantardasha",
                                        "type": "end",
                                        "planet": pratyantar.planet,
                                        "timestamp": pratyantar.end_date.isoformat(),
                                        "parent": f"{maha.planet}-{antar.planet}",
                                    }
                                )

        # Sort by timestamp
        changes.sort(key=lambda x: x["timestamp"])

        return changes

    def calculate_full_cycle(
        self,
        birth_time: datetime,
        moon_longitude: float | None = None,
        levels: int = 3,
    ) -> DashaPeriod:
        """
        Calculate full 120-year cycle with nested periods.

        Args:
            birth_time: Birth UTC timestamp
            moon_longitude: Pre-calculated Moon longitude (optional)
            levels: Depth of nesting (1-5)

        Returns:
            Root DashaPeriod with nested sub-periods
        """
        # Generate mahadashas
        mahadashas = self.generate_mahadashas(birth_time, moon_longitude, 120)

        # Add nested periods based on requested levels
        for maha in mahadashas:
            if levels >= 2:
                maha.sub_periods = self.calculate_antardashas(maha)

                if levels >= 3:
                    for antar in maha.sub_periods:
                        antar.sub_periods = self.calculate_pratyantar(antar)

                        if levels >= 4:
                            for pratyantar in antar.sub_periods:
                                pratyantar.sub_periods = self.calculate_sookshma(
                                    pratyantar
                                )

                                if levels >= 5:
                                    for sookshma in pratyantar.sub_periods:
                                        sookshma.sub_periods = self.calculate_prana(
                                            sookshma
                                        )

        # Create root period containing full cycle
        root = DashaPeriod(
            level="root",
            planet="CYCLE",
            start_date=mahadashas[0].start_date,
            end_date=mahadashas[-1].end_date,
            duration_days=Decimal(str(120 * 365.25)),
            sub_periods=mahadashas,
        )

        return root


# Module-level instance for convenience
_engine = None


def get_dasha_engine(ephe_path: str = "./swisseph/ephe") -> VimshottariDashaEngine:
    """Get or create singleton dasha engine instance"""
    global _engine
    if _engine is None:
        _engine = VimshottariDashaEngine(ephe_path)
    return _engine
