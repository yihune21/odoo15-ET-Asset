from odoo import fields, models
from dateutil.relativedelta import relativedelta
from odoo.tools import float_round
import calendar

class AccountAsset(models.Model):
    _inherit = 'account.asset.asset'

    fiscal_year_start_date = fields.Date(string='Fiscal Year Start Date')

    def _create_depreciation_line(self, date_from, date_to, depreciation_amount):
        """ Helper method to create a single depreciation line """
        return {
            'amount': depreciation_amount,
            'date_from': date_from,
            'date_to': date_to,
        }

    def compute_depreciation_board(self):
        """ Override to add July split functionality and calculate depreciation until the end of the selected month """
        super(AccountAsset, self).compute_depreciation_board()

        commands = []
        sequence = 1  # Initialize sequence
        total_depreciation = 0  # Initialize total depreciation

        for asset in self:
            remaining_value = asset.value_residual
            posted_depreciations = asset.depreciation_line_ids.filtered(lambda l: l.move_check)
            unposted_depreciations = asset.depreciation_line_ids.filtered(lambda l: not l.move_check)

            # Clear existing unposted depreciation lines
            commands += [(2, unposted_depreciation.id, 0) for unposted_depreciation in unposted_depreciations]

            # Use create_date or another relevant field for the start date of depreciation
            if asset.date_first_depreciation == 'last_day_period':
                start_date = asset.date
            else:
                start_date = asset.first_depreciation_manual_date

            current_date = start_date
            depreciation_day = current_date.day  # Remember the day of the first depreciation date

            # Iterate over the number of periods left for depreciation
            for i in range(asset.method_number):
                depreciation_amount = float_round(remaining_value / (asset.method_number - i), precision_digits=2)

                if current_date.month == 7:  # Handle the special case for July split (1-7 and 8-31)
                    # July 1-7
                    july_1_7_days = 7
                    july_days_total = 31
                    july_1_7_amount = depreciation_amount * (july_1_7_days / july_days_total)
                    total_depreciation += july_1_7_amount  # Update total depreciation
                    remaining_value_after_july_1_7 = remaining_value - july_1_7_amount

                    line_1 = {
                        'amount': july_1_7_amount,
                        'depreciation_date': current_date.replace(day=7),  # Set to July 7
                        'name': f'{asset.name} Depreciation July 1-7',
                        'sequence': sequence,
                        'remaining_value': remaining_value_after_july_1_7,
                        'depreciated_value': total_depreciation,  # Add cumulative depreciation
                    }
                    commands.append((0, 0, line_1))
                    sequence += 1

                    # Move current_date to July 8
                    current_date = current_date.replace(day=8)

                    # July 8-31
                    july_8_31_days = 24  # Days from July 8 to 31
                    july_8_31_amount = depreciation_amount * (july_8_31_days / july_days_total)
                    total_depreciation += july_8_31_amount  # Update total depreciation
                    remaining_value_after_july_8_31 = remaining_value_after_july_1_7 - july_8_31_amount

                    line_2 = {
                        'amount': july_8_31_amount,
                        'depreciation_date': current_date.replace(day=31),  # Set to July 31
                        'name': f'{asset.name} Depreciation July 8-31',
                        'sequence': sequence,
                        'remaining_value': remaining_value_after_july_8_31,
                        'depreciated_value': total_depreciation,  # Add cumulative depreciation
                    }
                    commands.append((0, 0, line_2))
                    sequence += 1

                    # Update remaining value for the next iteration
                    remaining_value = remaining_value_after_july_8_31

                    # Move current_date to the next month (August) while maintaining the depreciation_day
                    current_date = current_date + relativedelta(months=1)
                    current_date = self._adjust_date_day(current_date, depreciation_day)

                else:
                    # Handle all other months, including user-selected start date
                    last_day_of_month = calendar.monthrange(current_date.year, current_date.month)[1]

                    # For the first month, handle the case where depreciation starts mid-month
                    if current_date.day != 1:
                        days_in_month = last_day_of_month
                        days_for_depreciation = days_in_month - current_date.day + 1
                        depreciation_fraction = days_for_depreciation / days_in_month
                        depreciation_amount = depreciation_amount * depreciation_fraction

                    total_depreciation += depreciation_amount  # Update total depreciation

                    line = {
                        'amount': depreciation_amount,
                        'depreciation_date': current_date.replace(day=last_day_of_month),
                        'name': f'{asset.name} Depreciation {current_date.strftime("%B %Y")}',
                        'sequence': sequence,
                        'remaining_value': remaining_value - depreciation_amount,
                        'depreciated_value': total_depreciation,  # Add cumulative depreciation
                    }
                    commands.append((0, 0, line))
                    sequence += 1

                    # Update remaining value for the next iteration
                    remaining_value -= depreciation_amount

                    # Move current_date to the 1st day of the next month
                    current_date = current_date + relativedelta(months=1, day=1)

        asset.write({'depreciation_line_ids': commands})

    def _adjust_date_day(self, date, day):
        """ Adjusts the day of the date, considering February and months with fewer days """
        try:
            # Try setting the day directly
            return date.replace(day=day)
        except ValueError:
            # If day is out of range (e.g., Feb 30 or Apr 31), set it to the last day of the month
            return date + relativedelta(day=31)
